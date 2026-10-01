"""CLI entry point -- the whole pipeline in one command.

    python src/ask.py --offline Q1     # no API key needed
    python src/ask.py --offline Q2     # diagnostic: attribution + comparison window
    python src/ask.py --list
    python src/ask.py "on-time delivery for India warehouses last month"

Two paths, one pipeline. `--offline` swaps a hand-authored intent in where the resolver
would sit; every other stage is identical. That is the demonstration, not a convenience:
if the offline and online paths shared only the printing code, the offline numbers would
prove nothing about the system that serves the online ones.

The order of operations is the governance story:

    retriever -> resolver -> VALIDATE -> compile -> execute -> DQ -> answer

Validation happens before compilation, so a refused intent never becomes SQL. The DQ run
happens after execution but gates the *presentation*: a BLOCKED badge replaces the number
with a refusal rather than annotating it, because a caveated wrong number still gets
pasted into a slide with the caveat trimmed off.

This module prints refusals as loudly as answers. A layer that says "I can't answer that,
here is which rule stopped me" is more useful than one that always produces a number, and
the exit code is non-zero so a script can tell the difference.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

# Run-as-script bootstrap. `python src/ask.py` puts `src/` on sys.path, not the repo
# root, so the absolute imports below would fail; `python -m src.ask` is fine either
# way. This has to happen before the first `src.` import, not in __main__.
if __package__ in (None, ""):  # pragma: no cover -- depends on invocation form
    from pathlib import Path as _Path

    _root = str(_Path(__file__).resolve().parents[1])
    if _root not in sys.path:
        sys.path.insert(0, _root)

from src.semantic.compiler import CompilerError, compile_sql
from src.semantic.constants import DB_PATH
from src.semantic.dq import run_rules
from src.semantic.executor import run
from src.semantic.intent import QueryIntent
from src.semantic.loader import load_semantic_model, SemanticModel
from src.semantic.provenance import Answer, build_answer, phase_labels
from src.semantic.retriever import build_context, golden_intent, load_golden_intents
from src.semantic.validator import GATE_NAMES, validate


@dataclass
class AskResult:
    """An answer, its comparison window if one was asked for, and the delta.

    `delta` is stored rather than recomputed at print time so there is exactly one
    subtraction in the codebase. Two call sites computing "the drop" is how a headline
    and a chart end up disagreeing by a rounding step.
    """

    answer: Answer
    comparison: Answer | None = None
    delta: float | None = None
    question: str = ""


# Wide enough for the longest gate name plus a gap. Derived, not typed as a literal:
# `time_window_bounded` is 19 characters and a hardcoded 14 glued the gate name to its
# own message, making the longest refusal the least readable one.
_LABEL_WIDTH = max(len(g) for g in GATE_NAMES) + 2


def _labelled(label: str, message: str, width: int = _LABEL_WIDTH) -> list[str]:
    """`  label   message`, wrapped, with continuation lines under the message column.

    Gate messages name the offending value and the reason, so they are long by design --
    that is what makes a refusal actionable. Wrapping them keeps the refusal legible in
    an 88-column terminal instead of forcing a horizontal scroll.
    """
    import textwrap

    indent = " " * (2 + width)
    body = textwrap.wrap(message, width=88 - len(indent)) or [""]
    return [f"  {label:<{width}}{body[0]}"] + [f"{indent}{line}" for line in body[1:]]


def _ensure_warehouse() -> None:
    """Build the mart if it is missing.

    A reader's first command should work. Rebuilding is deterministic -- frozen seed,
    frozen as-of date -- so doing it implicitly cannot change an answer.
    """
    if not DB_PATH.exists():
        from src import build_warehouse

        print(f"[building warehouse at {DB_PATH.name} ...]", file=sys.stderr)
        build_warehouse.build()


# --------------------------------------------------------------------------------------
# the pipeline
# --------------------------------------------------------------------------------------


def _execute(qi: QueryIntent, model: SemanticModel) -> Answer:
    """compile -> execute -> DQ -> answer, for one window.

    Assumes the intent has already been validated. Splitting this out is what lets the
    comparison window reuse the identical path: the prior period is not a special case,
    it is the same query with different dates.
    """
    cq = compile_sql(qi, model)
    rows = run(cq)
    dq_report = run_rules(qi.metric)
    gates = validate(qi, model).gate_results
    return build_answer(qi, cq, rows, model, dq_report=dq_report, gate_results=gates)


def answer_intent(qi: QueryIntent, model: SemanticModel) -> tuple[int, str]:
    """Validate, run, and render one intent. Returns (exit_code, text).

    Returns text instead of printing so the refusal paths are testable without capturing
    stdout, and so a caller embedding this layer gets the same string the CLI prints.

    Three ways this returns a refusal instead of a number, in the order they can occur:

    1. A gate fails      -- the intent is not compiled at all.
    2. The compiler refuses -- a hazard the gates describe but the compiler must not
       emit SQL for (an unmaterialized entity, a fan-out join). Reaching here means the
       two disagree, which is a bug worth surfacing loudly rather than papering over.
    3. The DQ badge is BLOCKED -- the query was fine, the data is not.
    """
    result = validate(qi, model)
    if not result.ok:
        failed = [g for g, ok in sorted(result.gate_results.items()) if not ok]
        missing = [g for g in GATE_NAMES if g not in result.gate_results]
        lines = [
            f"REFUSED  {qi.metric}: the intent did not pass validation.",
            "",
            f"  gates failed  {', '.join(failed) or 'gate run incomplete'}",
        ]
        for f in result.failures:
            lines += _labelled(f.gate, f.message)
        if missing:
            lines.append(
                "  note          a gate did not run; an unevaluated gate fails closed."
            )
        lines += [
            "",
            "  No number is shown. A value that failed a gate is not a caveated answer,",
            "  it is an unverified one.",
        ]
        return 1, "\n".join(lines)

    try:
        answer = _execute(qi, model)
    except CompilerError as exc:
        return 1, (
            f"REFUSED  {qi.metric}: the query passed the gates but could not be "
            f"compiled.\n\n  reason        {exc}\n\n"
            "  This is a disagreement between the validator and the compiler. The\n"
            "  compiler refusing is the safe outcome; the mismatch is a defect."
        )

    if answer.trust_badge == "BLOCKED":
        return 1, (
            f"REFUSED  {answer.metric}: data quality is BLOCKED.\n\n"
            f"  failing rules {', '.join(answer.failing_rules)}\n"
            f"  metric        {answer.metric_definition}\n\n"
            "  A blocking rule means the mart cannot support this metric right now.\n"
            "  The value was computed and is deliberately not shown."
        )

    return 0, answer.render()


def answer_offline(qid: str, model: SemanticModel | None = None) -> AskResult:
    """Run one golden intent end to end. No API key, no network.

    A diagnostic intent carrying a `comparison` window runs twice: once for the asked
    period and once for the prior one. The comparison is deliberately run *ungrouped* --
    the breakdown answers "which phase", the prior window answers "compared with what",
    and grouping the prior period too would produce a second breakdown nobody asked for.
    """
    _ensure_warehouse()
    model = model or load_semantic_model()
    qi = golden_intent(qid)

    result = validate(qi, model)
    if not result.ok:  # pragma: no cover -- every golden intent passes; guarded anyway
        failed = [g for g, ok in result.gate_results.items() if not ok]
        raise ValueError(f"golden intent {qid} fails gates: {failed}")

    answer = _execute(qi, model)

    comparison: Answer | None = None
    delta: float | None = None
    if qi.comparison is not None:
        # model_copy, not dataclasses.replace: QueryIntent is a Pydantic model, and
        # `replace` would raise. Re-validating the copy would also work; copying keeps
        # the prior window provably the same intent with two fields changed.
        prior_qi = qi.model_copy(
            update={"time_window": qi.comparison, "dimensions": [], "comparison": None}
        )
        comparison = _execute(prior_qi, model)
        if answer.value is not None and comparison.value is not None:
            delta = answer.value - comparison.value

    question = load_golden_intents().get(qid, {}).get("question", "")
    return AskResult(answer=answer, comparison=comparison, delta=delta, question=question)


# --------------------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------------------


def render_result(result: AskResult) -> str:
    """The full printed block, including the comparison paragraph when there is one."""
    lines = []
    if result.question:
        lines += [f'QUESTION "{result.question}"', ""]
    lines.append(result.answer.render())

    if result.comparison is not None:
        prior = result.comparison
        lines += ["", "  COMPARISON"]
        lines.append(
            f"    prior window               {prior.window or 'n/a'}"
        )
        lines.append(
            f"    prior value                {prior.display_value} "
            f"({prior.numerator} / {prior.denominator})"
        )
        if result.delta is not None:
            direction = "down" if result.delta < 0 else "up"
            lines.append(
                f"    change                     {direction} "
                f"{abs(result.delta):.1f}pp "
                f"({prior.display_value} -> {result.answer.display_value})"
            )
            lines += [
                "",
                "  The change is computed from summed numerators and denominators, not"
                " from",
                "  an average of the per-phase rates -- averaging rates across groups of"
                " unequal",
                "  size gives a different, wrong number.",
            ]
    return "\n".join(lines)


# --------------------------------------------------------------------------------------
# the online path
# --------------------------------------------------------------------------------------


def answer_question(question: str, model: SemanticModel | None = None) -> tuple[int, str]:
    """Resolve a natural-language question through the API, then run the same pipeline.

    The resolver import is lazy on purpose. Offline mode is the path a reader without a
    key uses to run the whole system, and a module-scope import of the vendor SDK would
    let a missing or broken install take that path down with it. There is a test asserting
    the SDK is absent from `sys.modules` after an offline run.
    """
    _ensure_warehouse()
    model = model or load_semantic_model()
    context = build_context(question, model)

    try:
        from src.semantic import resolver
    except ImportError as exc:  # pragma: no cover -- depends on the local install
        return 2, (
            f"The resolver needs the Anthropic SDK, which failed to import: {exc}\n"
            "  pip install -r requirements.txt\n"
            "Offline mode needs no SDK and no key:  python src/ask.py --offline Q1"
        )

    try:
        qi = resolver.resolve(question, context)
    except resolver.ResolverRefusal as exc:
        return 1, (
            f'REFUSED  "{question}"\n\n  reason        {exc}\n\n'
            "  The question could not be mapped onto an approved metric. This is the\n"
            "  intended outcome for a question the governed model does not cover."
        )
    except resolver.ResolverAuthError as exc:
        return 2, (
            f"No usable API credentials: {exc}\n\n"
            "  Check with:   ant auth status\n"
            "  Or run without a key:  python src/ask.py --offline Q1"
        )
    except resolver.ResolverError as exc:
        return 2, f"The resolver failed: {exc}\n\nTry:  python src/ask.py --offline Q1"

    return answer_intent(qi, model)


# --------------------------------------------------------------------------------------
# argument handling
# --------------------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ask",
        description="Ask a governed question in natural language.",
        epilog="Offline mode needs no API key and is the fastest way to see the "
        "pipeline end to end.",
    )
    parser.add_argument("question", nargs="?", help="the question, in quotes")
    parser.add_argument("--offline", metavar="QID",
                        help="run a stored intent (see --list) with no API call")
    parser.add_argument("--list", action="store_true",
                        help="list the stored questions and exit")
    parser.add_argument("--context", action="store_true",
                        help="print the metadata context the resolver would see, "
                             "then exit -- the governance surface, reviewable without "
                             "a key")
    parser.add_argument("--sql", action="store_true",
                        help="also print the compiled SQL")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.list:
        intents = load_golden_intents()
        print("Stored questions (run with --offline QID):\n")
        for qid in sorted(intents):
            spec = intents[qid]
            print(f"  {qid}  {spec['question']}")
            note = spec.get("note")
            if note:
                print(f"      {note.split('.')[0]}.")
        return 0

    if args.context:
        question = args.question or "on-time delivery for India warehouses last month"
        print(build_context(question, load_semantic_model()))
        return 0

    if args.offline:
        try:
            result = answer_offline(args.offline)
        except KeyError as exc:
            # The message from `golden_intent` already lists what is available.
            print(str(exc).strip('"\''), file=sys.stderr)
            return 1
        print(render_result(result))
        if args.sql:
            print("\n  SQL\n")
            for line in result.answer.sql.splitlines():
                print(f"    {line}")
        return 0

    if not args.question:
        _build_parser().print_help()
        return 2

    code, text = answer_question(args.question)
    print(text, file=sys.stdout if code == 0 else sys.stderr)
    return code


if __name__ == "__main__":
    # Support both `python src/ask.py` and `python -m src.ask`. The former runs with
    # src/ on sys.path rather than the repo root, so `from src.semantic import ...`
    # would fail without this.
    raise SystemExit(main())
