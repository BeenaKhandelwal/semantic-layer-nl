"""Assemble `content/medium-post.md` from its prose template plus real code and real output.

The post's whole promise is "complete executable code". Two ways that promise breaks, and
neither is visible in the published page:

* The excerpts drift. Someone edits `standalone/semantic_layer_demo.py`, the post keeps
  quoting the old version, and a reader who copies an excerpt gets code that no longer
  matches the file it was extracted from.
* The output drifts. The post claims the script prints 87.3%; nobody re-runs it after a
  change, and the claim quietly becomes false.

So neither the code nor the output is typed into the template. Every `{{...}}` marker is
filled from the file on disk or from an actual run:

    {{CODE}}                     the entire standalone file, verbatim
    {{FUNC:name}}                one function's source, verbatim
    {{SNIP:start||end}}          the region between two literal anchors, inclusive
    {{OUTPUT:1}}                 section 1 of the script's real stdout, from a real run

`tests/test_content.py` asserts the file on disk equals what this script produces, so a
stale post fails the suite rather than misleading a reader.

Usage:
    python content/build_medium_post.py          # write content/medium-post.md
    python content/build_medium_post.py --check  # exit 1 if the file on disk is stale
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.semantic.constants import REPO_ROOT  # noqa: E402

TEMPLATE = REPO_ROOT / "content" / "medium-post.template.md"
OUT_MD = REPO_ROOT / "content" / "medium-post.md"
STANDALONE = REPO_ROOT / "standalone" / "semantic_layer_demo.py"


def _source() -> str:
    return STANDALONE.read_text(encoding="utf-8")


def _run_demo() -> str:
    """The script's real stdout. If it exits non-zero the post does not get built."""
    proc = subprocess.run([sys.executable, str(STANDALONE)],
                          capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise SystemExit(
            f"the demo exited {proc.returncode}; refusing to publish its output\n"
            f"{proc.stderr[-2000:]}"
        )
    return proc.stdout


def _func(name: str) -> str:
    """One top-level function or class, decorators included.

    Terminates on the next line that starts at column 0, scanning from the `def`/`class`
    line rather than from the first captured line -- otherwise a decorated definition ends
    immediately, because the `class` line itself is at column 0 and looks like the
    terminator. That bug shipped a one-line "excerpt" of `QueryIntent`.
    """
    src = _source()
    start = re.search(rf"^(?:@[\w.]+(?:\(.*?\))?\n)*(?:def|class) {re.escape(name)}\b",
                      src, re.M)
    if start is None:
        raise SystemExit(f"{name!r} is not a top-level definition in {STANDALONE.name}")

    lines = src[start.start():].splitlines(keepends=True)
    head = next(i for i, ln in enumerate(lines) if re.match(r"(?:def|class) ", ln))
    body = lines[: head + 1]
    for line in lines[head + 1:]:
        if line.strip() and not line[0].isspace():
            break
        body.append(line)
    out = "".join(body).rstrip()
    assert len(out.splitlines()) > 1, f"{name!r} extracted as a single line: {out!r}"
    return out


def _snip(spec: str) -> str:
    """The region between two literal anchors, inclusive of both."""
    first, last = spec.split("||")
    src = _source()
    if first not in src:
        raise SystemExit(f"anchor not found in {STANDALONE.name}: {first!r}")
    body = src[src.index(first):]
    if last not in body:
        raise SystemExit(f"closing anchor not found after {first!r}: {last!r}")
    return body[:body.index(last) + len(last)].rstrip()


def _output_sections(stdout: str) -> dict[str, str]:
    """Split the run into the numbered sections the script prints.

    Keyed by the leading number so the template refers to `{{OUTPUT:3}}` rather than to a
    title that would have to be kept in sync in two places.
    """
    rule = "=" * 78
    chunks = stdout.split(rule)
    sections: dict[str, str] = {}
    # Chunks alternate: title, body, title, body... after the leading blank.
    for i in range(1, len(chunks) - 1, 2):
        title = chunks[i].strip()
        body = chunks[i + 1].rstrip()
        key = title.split(".")[0].strip()
        sections[key] = f"{title}\n{rule}\n{body}".rstrip()
    return sections


def build() -> str:
    template = TEMPLATE.read_text(encoding="utf-8")
    sections = _output_sections(_run_demo())

    def replace(match: re.Match) -> str:
        kind, _, arg = match.group(1).partition(":")
        if kind == "CODE":
            return _source().rstrip()
        if kind == "FUNC":
            return _func(arg)
        if kind == "SNIP":
            return _snip(arg)
        if kind == "OUTPUT":
            if arg not in sections:
                raise SystemExit(f"the demo printed no section {arg!r}; "
                                 f"it printed {sorted(sections)}")
            return sections[arg]
        raise SystemExit(f"unknown marker {{{{{match.group(1)}}}}}")

    out = re.sub(r"\{\{([^}]+)\}\}", replace, template)
    leftover = re.findall(r"\{\{[^}]+\}\}", out)
    assert not leftover, f"unfilled markers: {leftover}"
    return out.rstrip() + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if the post on disk is not what this would write")
    args = ap.parse_args()

    built = build()
    if args.check:
        current = OUT_MD.read_text(encoding="utf-8") if OUT_MD.exists() else ""
        if current != built:
            raise SystemExit(f"{OUT_MD.name} is stale; run: python {Path(__file__).name}")
        print(f"{OUT_MD.name} is current")
        return

    OUT_MD.write_text(built, encoding="utf-8", newline="\n")
    print(f"{OUT_MD.relative_to(REPO_ROOT)}  ({len(built.splitlines())} lines, "
          f"{len(built) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
