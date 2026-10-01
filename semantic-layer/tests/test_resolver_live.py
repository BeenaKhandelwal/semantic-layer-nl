import os, inspect
import pytest

def _has_creds():
    return bool(os.environ.get("ANTHROPIC_API_KEY") or
                os.environ.get("ANTHROPIC_AUTH_TOKEN"))

live = pytest.mark.skipif(not _has_creds(),
                          reason="no Anthropic credentials configured")

# ---- these run WITHOUT credentials: they inspect the code, not the API ----

def test_resolver_module_imports_without_credentials():
    import src.semantic.resolver as r
    assert hasattr(r, "resolve")

def test_resolver_uses_correct_model_id():
    import src.semantic.resolver as r
    src = inspect.getsource(r)
    assert "claude-opus-5" in src

def test_resolver_uses_adaptive_thinking():
    import src.semantic.resolver as r
    src = inspect.getsource(r)
    assert '"adaptive"' in src or "'adaptive'" in src

def test_resolver_never_sends_forbidden_params():
    """temperature/top_p/top_k/budget_tokens all return HTTP 400 on Opus 5."""
    import src.semantic.resolver as r
    src = inspect.getsource(r)
    for forbidden in ("temperature", "top_p", "top_k", "budget_tokens"):
        assert forbidden not in src, f"resolver passes forbidden param {forbidden}"

def test_resolver_checks_refusal_stop_reason():
    import src.semantic.resolver as r
    assert "refusal" in inspect.getsource(r)

def test_resolver_uses_zero_arg_constructor():
    """Lets the SDK pick up whatever auth is configured."""
    import src.semantic.resolver as r
    assert "Anthropic()" in inspect.getsource(r)

def test_system_prompt_forbids_sql_generation():
    from src.semantic.resolver import SYSTEM_PROMPT
    low = SYSTEM_PROMPT.lower()
    assert "sql" in low
    assert "do not" in low or "never" in low

# ---- these need credentials ----

@live
def test_resolves_q1_to_the_golden_intent():
    from src.semantic.loader import load_semantic_model
    from src.semantic.resolver import resolve
    from src.semantic.retriever import golden_intent
    got = resolve("On-time delivery for India warehouses last month", load_semantic_model())
    want = golden_intent("Q1")
    assert got.metric == want.metric
    assert got.grain == want.grain
    assert got.time_window.start == want.time_window.start
    assert got.time_window.end == want.time_window.end
    assert {(f.column, str(f.value)) for f in got.filters} == \
           {(f.column, str(f.value)) for f in want.filters}

@live
def test_resolves_q2_as_diagnostic():
    from src.semantic.loader import load_semantic_model
    from src.semantic.resolver import resolve
    got = resolve("Why did on-time delivery drop for India warehouses last month?",
                  load_semantic_model())
    assert got.intent_type == "diagnostic"
    assert "delay_attribution_phase" in got.dimensions

@live
def test_resolved_intent_passes_the_validator():
    from src.semantic.loader import load_semantic_model
    from src.semantic.resolver import resolve
    from src.semantic.validator import validate
    model = load_semantic_model()
    r = validate(resolve("what was OTD in India in July 2026", model), model)
    assert r.ok, r.failures


# --- Added beyond the plan ---------------------------------------------------
# The plan's 7 offline tests are all source greps. A grep proves a string is
# present, not that the call is shaped correctly -- so these check the request
# actually built, and the failure handling, using a fake client. That keeps the
# whole resolver testable without credentials, which matters because the live
# tests skip in CI and would otherwise leave this module unexercised.

class _FakeMessages:
    """Records the kwargs `parse` was called with and returns a canned response."""

    def __init__(self, response=None, raises=None):
        self.response, self.raises, self.calls = response, raises, []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if self.raises is not None:
            raise self.raises
        return self.response


class _FakeClient:
    def __init__(self, response=None, raises=None):
        self.messages = _FakeMessages(response, raises)


class _FakeBlock:
    def __init__(self, parsed):
        self.type, self.parsed_output = "text", parsed


class _FakeResponse:
    """Mirrors `anthropic.types.ParsedMessage` closely enough to be falsifiable.

    The real `parsed_output` is a property that *iterates `self.content`* -- it is not a
    stored attribute. An earlier version of this fake returned a stored value instead, and
    that divergence made the refusal test vacuous: deleting the refusal check from the
    resolver still passed, because the `parsed is None` fallback caught it. So `content`
    raises on a refusal (reading it there is the bug under test) and `parsed_output` goes
    through `content`, which is what makes the ordering observable.
    """

    def __init__(self, parsed=None, stop_reason="end_turn"):
        self.stop_reason = stop_reason
        self._blocks = [_FakeBlock(parsed)] if parsed is not None else []

    @property
    def content(self):
        if self.stop_reason == "refusal":
            raise AssertionError(
                ".content was read on a refusal response; the refusal check must come "
                "first"
            )
        return self._blocks

    @property
    def parsed_output(self):
        for block in self.content:
            if block.type == "text" and block.parsed_output is not None:
                return block.parsed_output
        return None


def _golden():
    from src.semantic.retriever import golden_intent
    return golden_intent("Q1")


def test_the_question_is_not_baked_into_the_cached_system_block():
    """Cache correctness, and the reason context and question are separated.

    The metadata context is the stable prefix and is cached; the question is
    volatile. Concatenating them would make every question a cache miss, and
    would also let question text sit in the block the model treats as governed
    instructions -- a prompt-injection path straight into the metric list.
    """
    import src.semantic.resolver as r
    from src.semantic.loader import load_semantic_model
    question = "on-time delivery for India warehouses last month"
    client = _FakeClient(_FakeResponse(parsed=_golden()))
    r.resolve(question, load_semantic_model(), client=client)
    sent = client.messages.calls[0]

    system_text = " ".join(
        b["text"] if isinstance(b, dict) else str(b) for b in sent["system"]
    )
    assert "APPROVED METRICS" in system_text, "the governed context must be in system"
    assert question not in system_text, "the volatile question must not be cached"

    user_text = " ".join(
        c["text"] if isinstance(c, dict) else str(c)
        for m in sent["messages"] for c in (
            m["content"] if isinstance(m["content"], list) else [{"text": m["content"]}]
        )
    )
    assert question in user_text


def test_the_last_system_block_is_marked_for_caching():
    """Without a cache breakpoint the stable prefix is re-read on every call."""
    import src.semantic.resolver as r
    from src.semantic.loader import load_semantic_model
    client = _FakeClient(_FakeResponse(parsed=_golden()))
    r.resolve("anything", load_semantic_model(), client=client)
    system = client.messages.calls[0]["system"]
    assert isinstance(system, list) and system
    assert system[-1].get("cache_control", {}).get("type") == "ephemeral"


def test_a_refusal_stop_reason_raises_before_content_is_read():
    """`.content` on a refusal is undefined; reading it first is the classic bug.

    _FakeResponse.content raises if touched, so this fails loudly rather than
    passing for the wrong reason.
    """
    import src.semantic.resolver as r
    from src.semantic.loader import load_semantic_model
    client = _FakeClient(_FakeResponse(parsed=None, stop_reason="refusal"))
    with pytest.raises(r.ResolverRefusal):
        r.resolve("something the model declines", load_semantic_model(), client=client)


def test_an_auth_failure_is_distinguishable_from_a_bad_question():
    """The CLI prints different guidance for each, so they cannot share a type.

    Collapsing them would tell a user with an expired key to rephrase their
    question, and a user asking an unanswerable question to check their key.
    """
    import anthropic
    import src.semantic.resolver as r
    from src.semantic.loader import load_semantic_model
    import httpx
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    err = anthropic.AuthenticationError(
        "invalid x-api-key",
        response=httpx.Response(401, request=request),
        body=None,
    )
    client = _FakeClient(raises=err)
    with pytest.raises(r.ResolverAuthError):
        r.resolve("anything", load_semantic_model(), client=client)
    assert issubclass(r.ResolverAuthError, r.ResolverError)
    assert issubclass(r.ResolverRefusal, r.ResolverError)


def test_the_resolver_returns_a_parsed_intent_not_free_text():
    """The whole architecture rests on this boundary.

    If the resolver could return prose, something downstream would have to parse
    it, and that parser would become an ungoverned second interpreter of the
    question.
    """
    import src.semantic.resolver as r
    from src.semantic.intent import QueryIntent
    from src.semantic.loader import load_semantic_model
    client = _FakeClient(_FakeResponse(parsed=_golden()))
    got = r.resolve("on-time delivery for India last month",
                    load_semantic_model(), client=client)
    assert isinstance(got, QueryIntent)
    assert got.metric == "on_time_delivery_pct"


def test_the_resolver_asks_for_the_intent_schema_not_a_text_completion():
    """Structured output is requested at the API layer, so a shape mismatch is
    retried by the SDK rather than arriving as unparseable prose."""
    import src.semantic.resolver as r
    from src.semantic.intent import QueryIntent
    from src.semantic.loader import load_semantic_model
    client = _FakeClient(_FakeResponse(parsed=_golden()))
    r.resolve("anything", load_semantic_model(), client=client)
    sent = client.messages.calls[0]
    assert sent["output_format"] is QueryIntent
    assert sent["model"] == r.MODEL
    assert sent["thinking"] == {"type": "adaptive"}


def test_a_context_can_be_passed_in_so_the_cli_does_not_build_it_twice():
    """`ask.py --context` prints the same string the resolver sends.

    If the CLI's preview and the resolver's request were built by separate
    calls, the reviewable artifact could drift from the one actually sent.
    """
    import src.semantic.resolver as r
    from src.semantic.loader import load_semantic_model
    from src.semantic.retriever import build_context, split_context
    model = load_semantic_model()
    context = build_context("a question", model)
    client = _FakeClient(_FakeResponse(parsed=_golden()))
    r.resolve("a question", model, context=context, client=client)
    system_text = " ".join(b["text"] for b in client.messages.calls[0]["system"])
    governed, _ = split_context(context)
    # The governed prefix is sent verbatim; the question tail is not, because it
    # travels in the user turn. Asserting the whole string would demand the very
    # thing the cache split forbids.
    assert governed in system_text
    assert governed  # not vacuous: the split must actually yield a prefix


def test_the_cached_prefix_is_byte_identical_across_different_questions():
    """The point of the split: two questions must produce the same cached blocks.

    Found while reading the built request. A prefix that varies per question is
    a cache breakpoint that never hits -- the cost of caching with none of the
    benefit -- and the failure is invisible, since the answers stay correct.
    """
    import src.semantic.resolver as r
    from src.semantic.loader import load_semantic_model
    model = load_semantic_model()
    sent = []
    for question in ("on-time delivery for India last month",
                     "why did OTD drop in July?"):
        client = _FakeClient(_FakeResponse(parsed=_golden()))
        r.resolve(question, model, client=client)
        sent.append(client.messages.calls[0])
    assert sent[0]["system"] == sent[1]["system"], "the cached prefix varies by question"
    assert sent[0]["messages"] != sent[1]["messages"], "the question must still vary"


def test_the_system_prompt_does_not_reference_a_section_it_no_longer_carries():
    """The prompt described "the text after ## QUESTION" while the split moved
    that text into the user turn -- instructions about a section the model cannot
    see are how a prompt starts lying about its own contents."""
    import src.semantic.resolver as r
    from src.semantic.retriever import QUESTION_HEADER
    from src.semantic.loader import load_semantic_model
    client = _FakeClient(_FakeResponse(parsed=_golden()))
    r.resolve("a question", load_semantic_model(), client=client)
    system_text = " ".join(b["text"] for b in client.messages.calls[0]["system"])
    assert QUESTION_HEADER not in system_text
    assert QUESTION_HEADER not in r.SYSTEM_PROMPT


def test_the_resolver_is_the_only_module_that_names_the_vendor_sdk():
    """Structural: one module holds the model dependency, so the rest of the
    pipeline stays reviewable and runnable without a key."""
    from src.semantic.constants import REPO_ROOT
    offenders = []
    for path in sorted((REPO_ROOT / "src").rglob("*.py")):
        if path.name == "resolver.py":
            continue
        if "anthropic" in path.read_text(encoding="utf-8"):
            offenders.append(path.name)
    # ask.py imports the resolver lazily and names it in prose only; assert it
    # does not import the SDK itself.
    assert offenders == [], f"the SDK leaked into {offenders}"
