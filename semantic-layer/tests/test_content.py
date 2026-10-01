"""The published copy is under test too, because it is the part strangers read first.

README.md is already pinned to the artifacts by test_guide.py. `content/` was not, and
it is the higher-risk surface: a LinkedIn post and an article get edited for rhythm,
trimmed for length, and rewritten after feedback, none of which touches a test. A figure
that drifts there is a figure a reader cannot reproduce from the repo the post links to,
which spends exactly the credibility the post is trying to build.

So these tests do to the public copy what test_guide.py does to the guide: every number
in it has to be a number the pipeline actually prints, and the counts it quotes have to
match the artifacts it is describing.

Deliberately NOT tested: tone, length, hook quality, hashtags. Those are judgement, and a
test asserting them would just be my opinion wearing a lab coat.
"""
import re

import pytest

from src.semantic.constants import REPO_ROOT

CONTENT = REPO_ROOT / "content"
ARTICLE = CONTENT / "linkedin-article.md"
POST = CONTENT / "linkedin-post.md"
MEDIUM = CONTENT / "medium-post.md"


def _article():
    return ARTICLE.read_text(encoding="utf-8")


def _post():
    return POST.read_text(encoding="utf-8")


def _medium():
    return MEDIUM.read_text(encoding="utf-8")


def _prose(text):
    """The document with fenced code blocks removed.

    Prose rules and code rules are different rules. `INSERT ` is a placeholder in prose and
    a SQL keyword in a fence; `{value:.1f}%` is a format string, not a claim. Scanning both
    with one ruleset means either the code trips the prose checks or the prose checks get
    weakened until they stop catching anything.
    """
    return re.sub(r"^```.*?^```", "", text, flags=re.S | re.M)


@pytest.mark.parametrize("path", [ARTICLE, POST, MEDIUM])
def test_the_published_copy_exists_and_is_substantial(path):
    assert path.exists(), f"{path.name} is missing"
    assert len(path.read_text(encoding="utf-8")) > 900, f"{path.name} looks truncated"


@pytest.mark.parametrize("path", [ARTICLE, POST, MEDIUM])
def test_no_placeholders_in_published_copy(path):
    text = _prose(path.read_text(encoding="utf-8"))
    for bad in ("TBD", "TODO", "FIXME", "XXX", "Lorem ipsum", "<placeholder>",
                "[link]", "INSERT "):
        assert bad not in text, f"{path.name} contains {bad}"


def test_the_three_parts_are_distinct_documents_not_three_copies():
    """The ask was three deliverables for three surfaces, not one text posted thrice.

    Checked crudely but usefully: each pair must differ in length by enough that one is
    not a lightly-edited paste of another, and each must carry the thing that makes it
    that surface -- the post an image note, the article the figures, the post-with-code
    the code.
    """
    lengths = {p.name: len(p.read_text(encoding="utf-8"))
               for p in (POST, ARTICLE, MEDIUM)}
    assert lengths["linkedin-post.md"] < lengths["linkedin-article.md"] < \
        lengths["medium-post.md"], lengths
    assert "Notes for posting" in _post()
    assert "![" in _article(), "the article embeds no figure"
    assert "```python" in _medium(), "the medium post carries no code"


# --- the figures ---------------------------------------------------------------
# Every number both files quote, and where it comes from. The point of listing them
# here rather than asserting "some percentage appears" is that a wrong figure in the
# post is indistinguishable from a right one to any reader who does not clone the repo.

CANONICAL = {
    "87.3%": "the grain-correct OTD answer, 48/55",
    "88.5%": "the naive delivery-grain answer, 54/61",
    "48": "on-time orders at order grain",
    "55": "eligible orders",
    "61": "delivery legs -- the reason the two numbers differ",
    "96.2%": "the June comparison window, 25/26",
    "8.9": "the drop in percentage points",
    "4.75": "average QM overrun in days",
}


@pytest.mark.parametrize("figure", sorted(CANONICAL))
def test_every_canonical_figure_appears_in_the_article(figure):
    assert figure in _article(), (
        f"the article no longer quotes {figure} ({CANONICAL[figure]})"
    )


def test_the_post_quotes_the_two_numbers_the_whole_argument_rests_on():
    """The post is short enough that not every figure fits. These two must."""
    text = _post()
    for figure in ("88.5%", "87.3%", "61", "55", "8.9pp", "4.75"):
        assert figure in text, f"the post no longer quotes {figure}"


def test_no_stray_percentage_in_the_published_copy_is_uncanonical():
    """Catches the invented figure, which is the failure mode prose actually has.

    A drifted number is usually not a mangled digit -- it is a plausible new
    percentage that appeared during an edit ("about 12% of orders...") and was never
    measured. Anything quoted as a percentage has to be on the allow-list, and adding
    to the allow-list means having measured it first.
    """
    allowed = {
        "87.3", "87.27", "88.5", "88.52",   # OTD, correct and naive
        "96.2",                             # June comparison
        "94.4", "94.44", "94.5", "94.55",   # FPY, correct and naive
        "92.6", "92.59",                    # schedule adherence
        "2.0", "2",                         # the DQ completeness threshold
        "100",                              # rhetorical / whole
        # The three-order hand count in the on-ramp: 2 of 3 orders against 3 of 4
        # shipments. Measured, not chosen -- tests/test_diagram.py recomputes both from
        # the rows the post ships (test_the_hand_countable_example_...).
        "66.7", "75.0",
    }
    for path, text in (("linkedin-article.md", _prose(_article())),
                       ("linkedin-post.md", _prose(_post())),
                       ("medium-post.md", _prose(_medium()))):
        for raw in re.findall(r"(\d+(?:\.\d+)?)\s?%", text):
            assert raw in allowed, (
                f"{path} quotes {raw}% which is not a measured figure from this "
                f"project; if it is real, measure it and add it to the allow-list"
            )


def test_the_delta_between_the_two_headline_numbers_is_stated_correctly():
    """88.52 - 87.27 = 1.25. If either number is edited, this catches the stale delta."""
    text = _article()
    assert "1.25" in text, "the article states the two numbers but not the gap"
    assert abs((54 / 61 * 100) - (48 / 55 * 100) - 1.25) < 0.005


def test_the_provenance_counts_match_the_diagram_they_describe():
    """The article's 1 / 4 / 4 table is a claim about ARTIFACTS in render_sources.py."""
    from docs.diagrams.render_sources import ARTIFACTS
    counts = {k: sum(1 for a in ARTIFACTS if a["kind"] == k)
              for k in ("harvested", "derived", "authored")}
    assert counts == {"harvested": 1, "derived": 4, "authored": 4}, counts

    text = _article()
    for kind in ("HARVESTED", "DERIVED", "AUTHORED"):
        assert kind in text, f"the article's provenance table omits {kind}"
    # The load-bearing sentence, in whatever phrasing survives editing.
    assert re.search(r"one of the nine|1 of 9|only ONE", text, re.I), \
        "the article no longer states how many artifacts are harvestable"


def test_the_query_time_artifact_count_is_right():
    """Written after getting this wrong: I said five, and P3-P7 is six files."""
    from docs.diagrams.render_sources import ARTIFACTS
    query_time = [a for a in ARTIFACTS if a["use"] == "query"]
    assert len(query_time) == 6, [a["file"] for a in query_time]
    text = _article()
    assert "six artifacts sit in" in text, (
        "the article's hot-path count no longer says six; P3-P7 is six files, not "
        "five, because P3 emits two"
    )


def test_the_metric_count_the_article_quotes_is_the_approved_count():
    """Written after getting this wrong: the article said the model picks between *four*
    approved metrics.

    The P0 contract defines four; only three reached `approval_state: approved`, because
    `production_cycle_time_days` was deliberately deferred. Quoting the contract's number
    while describing what the retriever offers overstates the built system by one metric
    -- a small error, and exactly the kind this project argues is the dangerous kind,
    since nothing in the prose looks wrong.
    """
    from src.semantic.loader import load_semantic_model
    approved = load_semantic_model().approved_metric_names()
    assert len(approved) == 3, approved

    claimed = re.search(
        r"which of (\w+) approved metrics", _article()
    )
    assert claimed, "the article no longer says how many approved metrics the model picks from"
    words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
    assert words.get(claimed.group(1).lower()) == len(approved), (
        f"the article says the model picks between {claimed.group(1)!r} approved "
        f"metrics; the semantic model has {len(approved)}: {approved}"
    )


def test_the_refusal_the_article_prints_is_the_refusal_the_validator_prints():
    """The article's own argument is that plausible-looking output is the hazard, so a
    paraphrased refusal dressed in a code fence is the one thing it cannot afford.

    This reproduces the 88.5% query as a delivery-grain intent and asserts the article
    quotes the gate message verbatim. No warehouse needed: validation runs before
    compilation, so the refusal is produced without touching the database.
    """
    from src.ask import answer_intent
    from src.semantic.intent import Filter, QueryIntent, TimeWindow
    from src.semantic.loader import load_semantic_model

    rc, out = answer_intent(
        QueryIntent(
            intent_type="descriptive",
            metric="on_time_delivery_pct",
            grain="delivery",
            dimensions=[],
            filters=[Filter(column="region", operator="=", value="IN")],
            time_window=TimeWindow(start="2026-07-01", end="2026-07-31",
                                   label="July 2026"),
        ),
        load_semantic_model(),
    )
    assert rc == 1, f"the delivery-grain intent was not refused:\n{out}"

    text = _article()
    # Compare on collapsed whitespace: the article rewraps the message to its own
    # column width, which is presentation, not content.
    def flat(s):
        return " ".join(s.split())

    for sentence in (
        "Metric 'on_time_delivery_pct' is certified at grain 'order'; the intent asks "
        "for grain 'delivery'.",
        "Aggregating at the wrong grain changes the number.",
        "No number is shown. A value that failed a gate is not a caveated answer,",
    ):
        assert flat(sentence) in flat(out), f"the real refusal no longer says: {sentence}"
        assert flat(sentence) in flat(text), (
            f"the article's refusal block paraphrases the validator. It must quote it:\n"
            f"  missing: {sentence}"
        )


def test_the_article_embeds_both_figures_with_paths_that_resolve():
    """A broken image in published copy is worse than no image: it reads as neglect."""
    text = _article()
    embeds = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)
    assert len(embeds) >= 2, f"expected both diagrams embedded, found {embeds}"
    for rel in embeds:
        assert (CONTENT / rel).resolve().exists(), \
            f"article embeds {rel}, which does not resolve from content/"
    assert any("metadata_sources" in e for e in embeds), \
        "the article does not embed the metadata sourcing figure"
    assert any("nl_dataflow" in e for e in embeds), \
        "the article does not embed the dataflow figure"


def test_the_post_names_the_image_it_should_be_published_with():
    """The post is text; the figure is a separate upload. If the notes do not say
    which file, the wrong one gets attached or none does."""
    text = _post()
    assert "nl_dataflow.png" in text
    assert "metadata_sources.png" in text, \
        "the notes do not mention the sourcing figure as the alternative lead image"


def test_the_reproduction_commands_in_the_article_are_real():
    """A reader's first action is to paste these. Each must be a file that exists."""
    text = _article()
    for script in re.findall(r"python (\S+\.py)", text):
        assert (REPO_ROOT / script).exists(), \
            f"the article tells the reader to run {script}, which does not exist"


def test_the_article_does_not_claim_the_live_resolver_is_tested():
    """The one honesty constraint that matters, since it is the easiest to soften.

    verify_acceptance.py reports the live-resolver criterion as SKIP. Published copy
    that implies otherwise would be overclaiming exactly where the project's argument
    is that overclaiming is the problem.
    """
    text = _article()
    assert "not** asserted as tested" in text or "not asserted as tested" in text, \
        "the article no longer states that the live resolver path is untested here"
    assert "SKIP" in text, "the article does not name the SKIP verdict"


def test_the_test_count_quoted_in_the_article_is_the_real_count():
    """The article quotes a test count as evidence. Evidence has to be current."""
    import subprocess
    import sys
    claimed = re.search(r"(\d+) tests hold it in place", _article())
    assert claimed, "the article no longer quotes a test count"
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=180,
    ).stdout
    actual = re.search(r"(\d+) tests collected", out)
    assert actual, f"could not read a collected count:\n{out[-400:]}"
    assert int(claimed.group(1)) == int(actual.group(1)), (
        f"the article claims {claimed.group(1)} tests; pytest collects "
        f"{actual.group(1)}"
    )


def test_the_print_stylesheet_constrains_image_width():
    """Found by reading the rendered PDF, which no other test does.

    The stylesheet had no `img` rule, so Chrome printed the 21in-wide diagrams at
    their intrinsic size and CLIPPED the right third off the page -- silently, and
    specifically the band showing how the metadata is used. A figure that is missing
    half its content while looking complete is worse than no figure.
    """
    src = (REPO_ROOT / "docs" / "md2pdf.py").read_text(encoding="utf-8")
    css = src[src.index("CSS = "):src.index("def find_chrome")]
    assert "img {" in css, "the print stylesheet has no img rule; wide figures will clip"
    img_rule = css[css.index("img {"):]
    img_rule = img_rule[:img_rule.index("}")]
    assert "max-width" in img_rule and "100%" in img_rule, img_rule
    assert "height: auto" in img_rule, "without height:auto the figure distorts"


def test_each_embedded_figure_says_where_the_full_resolution_version_is():
    """Scaled to a page the labels are too small to read. Saying so, with a path, is
    the difference between a limitation and an oversight."""
    text = _article()
    for fig in ("nl_dataflow", "metadata_sources"):
        after = text.split(f"{fig}.svg)", 1)[1][:300]
        assert "Full resolution" in after, (
            f"the {fig} embed is not followed by a pointer to the full-size file"
        )


# --- the Medium post's one distinguishing promise: complete executable code ------
# The post's value is entirely that the code in it runs. Prose can be wrong and a reader
# shrugs; code that does not run is the thing they remember. These tests exist because
# nothing else in the repository would notice the post going stale.


def _fences(text, lang=None):
    return [body for tag, body in re.findall(r"^```(\w*)\n(.*?)^```", text,
                                             re.S | re.M)
            if lang is None or tag == lang]


def test_the_code_published_in_the_medium_post_is_the_code_under_test():
    """Byte-identical, not equivalent.

    `tests/test_standalone.py` runs `standalone/semantic_layer_demo.py`. If the post
    carries any other version of that file, then the tested code and the published code
    are two different programs and the test suite is guarding the wrong one.
    """
    from src.semantic.constants import REPO_ROOT

    source = (REPO_ROOT / "standalone" / "semantic_layer_demo.py").read_text(
        encoding="utf-8")

    complete = [f for f in _fences(_medium(), "python")
                if len(f.splitlines()) > 200]
    assert len(complete) == 1, (
        f"expected exactly one complete-file fence in the medium post, found "
        f"{len(complete)}"
    )
    assert complete[0].rstrip("\n") == source.rstrip("\n"), (
        "the code in the medium post is not byte-identical to "
        "standalone/semantic_layer_demo.py -- regenerate with "
        "`python content/build_medium_post.py`"
    )


def test_every_excerpt_in_the_medium_post_appears_verbatim_in_the_source():
    """An excerpt is a quotation. A paraphrased excerpt in a post about the dangers of
    plausible-looking output would be a self-inflicted wound.

    Applies to the code excerpts only; the console-output fences are checked by
    `test_the_medium_post_on_disk_is_current`, which reruns the demo.
    """
    from src.semantic.constants import REPO_ROOT

    source = (REPO_ROOT / "standalone" / "semantic_layer_demo.py").read_text(
        encoding="utf-8")

    excerpts = [f for f in _fences(_medium(), "python") if len(f.splitlines()) <= 200]
    excerpts += _fences(_medium(), "yaml")
    assert len(excerpts) >= 6, f"only {len(excerpts)} excerpts; the walkthrough is thin"

    for body in excerpts:
        assert body.rstrip("\n") in source, (
            "the medium post quotes code that is not in the standalone file:\n"
            f"{body.splitlines()[0]}"
        )


def test_the_medium_post_on_disk_is_current():
    """Regenerates from the template and compares. This runs the demo, so it also proves
    every console block in the post is output the script really produces."""
    import sys

    sys.path.insert(0, str(REPO_ROOT / "content"))
    from content.build_medium_post import build

    assert _medium() == build(), (
        "content/medium-post.md is stale -- run `python content/build_medium_post.py`"
    )


def test_the_medium_post_states_the_install_line_its_code_actually_needs():
    """A reader's first command. If it names the wrong packages they never see anything."""
    from src.semantic.constants import REPO_ROOT

    source = (REPO_ROOT / "standalone" / "semantic_layer_demo.py").read_text(
        encoding="utf-8")
    third_party = set(re.findall(r"^\s*import (duckdb|yaml|anthropic)", source, re.M))
    # anthropic is imported inside the live-resolver function, which the demo never calls.
    needed = {"duckdb": "duckdb", "yaml": "pyyaml"}
    install = re.search(r"pip install ([^\n`]+)", _medium())
    assert install, "the medium post never tells the reader what to install"
    named = set(install.group(1).split())
    for module in third_party & set(needed):
        assert needed[module] in named, (
            f"the code imports {module} but the install line says {sorted(named)}"
        )


def test_every_test_count_quoted_in_the_medium_post_is_the_real_count():
    """Every occurrence, not the first one.

    This test used to `search` rather than `findall`, and the post quotes the count
    twice: once in its own prose and once inside the embedded file's docstring. The
    prose was current and the docstring said 328. A review caught it, which is exactly
    the job the test was supposed to be doing -- so it now checks all of them, in the
    post and in the standalone file it embeds.
    """
    import subprocess
    import sys

    sources = {
        "medium-post.md": _medium(),
        "standalone/semantic_layer_demo.py": (
            REPO_ROOT / "standalone" / "semantic_layer_demo.py").read_text(
            encoding="utf-8"),
    }
    claims = {name: re.findall(r"and (\d+) tests", text)
              for name, text in sources.items()}
    for name, found in claims.items():
        assert found, f"{name} no longer quotes a test count"

    out = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=300,
    ).stdout
    actual = re.search(r"(\d+) tests collected", out)
    assert actual, f"could not read a collected count:\n{out[-400:]}"
    stale = {name: found for name, found in claims.items()
             if any(int(c) != int(actual.group(1)) for c in found)}
    assert not stale, (
        f"pytest collects {actual.group(1)} tests; these quote something else: {stale}"
    )


def test_the_medium_post_declares_what_it_elides():
    """The post ships a trimmed data slice and embedded variances. Saying so is what
    separates a simplified example from a misleading one."""
    text = _medium()
    for claim in ("embedded, not derived", "does not do", "not exercised here"):
        assert claim in text, f"the medium post no longer states: {claim!r}"
    assert "83 orders" in text and "87 delivery legs" in text, (
        "the medium post does not say how much data it actually ships"
    )


def test_the_medium_post_is_publishable_copy_not_working_notes():
    """Publishing instructions inside the published article are the tell that nobody read
    it as a reader. Tags, canonical URLs and image-upload notes belong to whoever presses
    publish, so they live in a checklist beside the post instead of inside it.
    """
    text = _medium()
    for leak in ("Notes for posting", "Tags:", "canonical URL", "Lead image",
                 "Do not post both"):
        assert leak not in text, (
            f"the medium post still contains the working note {leak!r}; move it to "
            f"content/medium-publishing-checklist.md"
        )

    checklist = CONTENT / "medium-publishing-checklist.md"
    assert checklist.exists(), "the publishing notes were removed, not relocated"
    body = checklist.read_text(encoding="utf-8")
    for topic in ("Tags", "Canonical", "Gist", "Images", "Pre-flight"):
        assert topic in body, f"the publishing checklist says nothing about {topic}"


def test_the_medium_post_opens_the_way_medium_expects():
    """Medium's importer takes the first H1 as the title and the next H2 as the subtitle.

    Get the shape wrong and the subtitle lands in the body, which costs the search snippet
    and the preview line -- the two pieces of text that decide whether the article is read
    at all.
    """
    lines = [ln for ln in _medium().splitlines() if ln.strip()]
    assert lines[0].startswith("# "), f"the post does not open with an H1: {lines[0]!r}"
    assert lines[1].startswith("## "), (
        f"no subtitle immediately after the title: {lines[1]!r}"
    )
    title = lines[0][2:]
    assert len(title) <= 80, f"the title is {len(title)} chars; search results truncate"
    assert not lines[2].startswith("#"), "a third heading before any prose reads as a stub"


def test_every_figure_the_medium_post_embeds_resolves_and_is_captioned():
    """A broken image reads as neglect, and an uncaptioned diagram in a technical post
    reads as decoration. Both are cheap to check and neither is visible in the markdown."""
    text = _medium()
    embeds = re.findall(r"!\[[^\]]*\]\(([^)]+)\)\n\n(\*?)", text)
    assert len(embeds) >= 2, f"expected both diagrams embedded, found {embeds}"
    for rel, caption_starts in embeds:
        assert (CONTENT / rel).resolve().exists(), \
            f"the medium post embeds {rel}, which does not resolve from content/"
        assert caption_starts == "*", f"the {rel} embed is not followed by a caption"


# --- the publication kit -------------------------------------------------------
# Publishing needs the copy in one hand and the code in the other, so the kit is the
# article with the 1,000-line fence lifted out and the checklist bound in behind it. Both
# are generated from medium-post.md, which is what keeps the byte-identity check above
# meaningful: one source of truth, everything else derived from it.

KIT = CONTENT / "medium-kit.md"
CODE = CONTENT / "medium-code.md"


def _kit_builders():
    import sys

    sys.path.insert(0, str(REPO_ROOT / "content"))
    from content.build_medium_kit import build_code, build_kit

    return build_kit, build_code


def test_the_publication_kit_on_disk_is_current():
    """A kit assembled from an older draft of the post is the whole hazard of a derived
    artifact: it looks finished and it is not what the tests checked."""
    build_kit, build_code = _kit_builders()
    for path, built in ((KIT, build_kit()), (CODE, build_code())):
        assert path.exists(), f"{path.name} is missing"
        assert path.read_text(encoding="utf-8") == built, (
            f"{path.name} is stale -- run `python content/build_medium_kit.py`"
        )


def test_the_kit_lifts_the_code_out_and_says_where_it_went():
    """Lifting the fence is only safe if the pointer replacing it is real. A kit that drops
    the code and does not say where it is now is worse than one that keeps it."""
    kit = KIT.read_text(encoding="utf-8")
    assert not [f for f in _fences(kit, "python") if len(f.splitlines()) > 200], \
        "the kit still carries the complete file; the whole point was to lift it out"
    assert "medium-code.pdf" in kit, "the kit does not name the companion file"
    assert "pip install duckdb pyyaml" in kit, \
        "the kit dropped the two commands a reader needs"

    source = (REPO_ROOT / "standalone" / "semantic_layer_demo.py").read_text(
        encoding="utf-8")
    complete = [f for f in _fences(CODE.read_text(encoding="utf-8"), "python")
                if len(f.splitlines()) > 200]
    assert len(complete) == 1, f"expected one complete-file fence, found {len(complete)}"
    assert complete[0].rstrip("\n") == source.rstrip("\n"), (
        "medium-code.md is not byte-identical to standalone/semantic_layer_demo.py"
    )


def test_the_kit_carries_the_publishing_checklist_and_the_medium_slots():
    """The two things the article cannot carry itself: which line goes in Medium's title
    field, and everything on the checklist."""
    kit = KIT.read_text(encoding="utf-8")
    for marker in ("TITLE —", "SUBTITLE —", "Pre-flight", "Canonical", "Tags"):
        assert marker in kit, f"the kit is missing {marker!r}"
    for path in (KIT, CODE):
        pdf = path.with_suffix(".pdf")
        assert pdf.exists() and pdf.stat().st_size > 4000, (
            f"{pdf.name} is missing or truncated -- run "
            f"`python content/build_medium_kit.py`"
        )


# --- the rendered copies -------------------------------------------------------
# Each part also ships as .html and .pdf, because "here is the post" in a review means a
# document somebody can open. A rendered copy that has drifted from its markdown is the
# failure mode worth a test: it looks published, and it quotes last week's numbers.


def _render_html(md_path):
    """`docs/md2pdf.render_html`, loaded by path -- `docs/` is not an import package."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_md2pdf_for_test", REPO_ROOT / "docs" / "md2pdf.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.render_html(md_path)


@pytest.mark.parametrize("path", [POST, ARTICLE, MEDIUM], ids=lambda p: p.stem)
def test_every_published_part_ships_a_rendered_html_and_pdf(path):
    for suffix in (".html", ".pdf"):
        rendered = path.with_suffix(suffix)
        assert rendered.exists(), (
            f"{rendered.name} is missing -- render it with "
            f"`python docs/md2pdf.py {path.as_posix()}`"
        )
        assert rendered.stat().st_size > 4000, f"{rendered.name} looks truncated"


@pytest.mark.parametrize("path", [POST, ARTICLE, MEDIUM], ids=lambda p: p.stem)
def test_the_rendered_html_is_what_the_markdown_renders_to_now(path):
    """Byte-for-byte against a fresh render, which is cheap and needs no browser.

    This is what makes a stale rendered copy fail the suite instead of getting emailed to
    somebody. The PDF is printed from this same HTML by the same command, so HTML that is
    current is real evidence about the PDF -- and the next test reads the PDF itself.
    """
    actual = path.with_suffix(".html").read_text(encoding="utf-8")
    assert actual == _render_html(path), (
        f"{path.with_suffix('.html').name} is stale -- re-render it from {path.name}"
    )


@pytest.mark.parametrize("path", [POST, ARTICLE, MEDIUM], ids=lambda p: p.stem)
def test_the_rendered_pdf_still_quotes_the_canonical_figures(path):
    """Read out of the printed PDF, not inferred from the markdown.

    Chrome is a separate process printing a separate file; nothing else in the suite would
    notice a PDF left behind by an earlier draft. Only the figures the document actually
    quotes are required, so this tightens or relaxes itself as the copy changes.
    """
    fitz = pytest.importorskip("fitz", reason="PyMuPDF is not installed")

    with fitz.open(path.with_suffix(".pdf")) as doc:
        printed = "".join(page.get_text() for page in doc)
    source = path.read_text(encoding="utf-8")

    missing = [f for f in sorted(CANONICAL) if f in source and f not in printed]
    assert not missing, (
        f"{path.with_suffix('.pdf').name} does not contain {missing}, which {path.name} "
        f"quotes -- the PDF was printed from an older draft"
    )


def test_the_three_documents_point_at_each_other():
    """Three deliverables that never reference each other are three orphans."""
    assert "medium" in _post().lower(), (
        "the LinkedIn post's notes do not mention the Medium post with the code"
    )
    assert "medium" in _article().lower(), (
        "the article does not point at the Medium post for the runnable code"
    )
    assert "linkedin" in _medium().lower(), (
        "the Medium post does not point back at the LinkedIn article"
    )


# --- the plain-English on-ramp ---------------------------------------------------
# The post has two audiences and one body: a reader who says "grain" at work, and a
# reader who has never needed the word. The second one gets the first 500 words, and
# these tests hold the two properties that make those words worth reading -- no
# vocabulary before it is defined, and a worked example that is real.

ON_RAMP = "## Start here: one order, two boxes"
GLOSSARY = "### Five words the rest of this post needs"


def _on_ramp() -> str:
    """The on-ramp section: from its heading to the TL;DR that follows it."""
    text = _medium()
    start = text.index(ON_RAMP)
    return text[start:text.index("**TL;DR**", start)]


def test_the_post_defines_its_vocabulary_before_the_technical_sections():
    """A layman meets 'grain' in a table, not in a YAML block.

    The failure this catches is an edit that moves or deletes the glossary: the words
    then first appear in the metadata section, where the reader who needed them has
    already left.
    """
    text = _medium()
    on_ramp = _on_ramp()
    assert GLOSSARY in on_ramp, "the five-word glossary is no longer in the on-ramp"
    for word in ("grain", "fan-out", "metric", "gate", "provenance"):
        assert f"**{word}**" in on_ramp, f"the glossary no longer defines {word!r}"
    # And the on-ramp really is prose: no code, no YAML, nothing to skip past.
    assert "```" not in on_ramp, "the on-ramp has grown a code fence"
    assert on_ramp.index(GLOSSARY) < text.index("## Where the wrong number comes from"),         "the glossary now sits after the section that uses the words"


def test_the_hand_counted_example_is_the_measured_one():
    """The three orders, their dates, and both small percentages.

    This is the most temptingly fudgeable paragraph in the post: three rows small
    enough that a wrong date would never be noticed, chosen to make a point. So the
    table is checked against the same declaration the figure draws from, which
    tests/test_diagram.py checks against the rows the post ships.
    """
    from docs.diagrams.render_grain import MINI, mini_counts
    on_ramp = _on_ramp()
    rows = re.findall(r"^\| `(SO-\d+)` \| (.+?) \| (\d+) \| (.+?) \|", on_ramp, re.M)
    assert len(rows) == len(MINI), f"expected {len(MINI)} example rows, found {rows}"
    for (order, promised, boxes, last), row in zip(rows, MINI):
        assert order == row["order"], (order, row["order"])
        assert promised == row["promised"].strftime("%d %b").lstrip("0"), promised
        assert int(boxes) == len(row["legs"]), (order, boxes)
        latest = max(leg["date"] for leg in row["legs"])
        assert last.startswith(latest.strftime("%d %b").lstrip("0")), (order, last)

    (ok_o, all_o), (ok_l, all_l) = mini_counts()["order"], mini_counts()["leg"]
    assert f"two of the three were on time — **{100 * ok_o / all_o:.1f}%**" in on_ramp
    assert f"Three of four — **{100 * ok_l / all_l:.1f}%**" in on_ramp


def test_the_post_leads_with_the_figure_a_newcomer_can_read():
    """Medium shows the first image beside the title in every feed.

    The pipeline diagram is the wrong one for that slot: it means nothing until you
    accept the premise. The lead has to be the figure that states the problem.
    """
    text = _medium()
    embeds = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)
    assert embeds, "the post embeds no figure"
    assert "grain_two_ways" in embeds[0], (
        f"the lead figure is {embeds[0]}; it should be the plain-English one")
    assert any("nl_dataflow" in e for e in embeds), "the pipeline figure is gone"
    assert any("metadata_sources" in e for e in embeds), "the sourcing figure is gone"
