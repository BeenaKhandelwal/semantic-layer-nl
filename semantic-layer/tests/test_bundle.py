"""The "everything" bundle has to actually contain everything.

This is the one document whose defect is invisible: a 70-page PDF that quietly omits
`06_dq_rules.yml` looks exactly like one that includes it. Nobody reads a bundle
end-to-end to find out. So the section list is asserted against the directory rather
than trusted, and the figures are asserted to resolve from where the bundle is written.

Deliberately NOT tested: page count, or the PDF itself. Rendering needs a browser and
the markdown is the part that can be wrong in a way a reader would not notice.
"""
import re

from src.semantic.constants import METADATA_DIR, REPO_ROOT

from docs.build_bundle import ARTIFACTS, DOCUMENTS, OUT_MD, build_markdown


def test_the_bundle_covers_every_metadata_artifact_on_disk():
    """If a tenth artifact is ever added, this fails until the bundle includes it."""
    on_disk = {p.name for p in METADATA_DIR.iterdir() if p.is_file()}
    declared = {name for name, _ in ARTIFACTS}
    assert declared == on_disk, (
        f"bundle/metadata mismatch — missing from the bundle: {sorted(on_disk - declared)}; "
        f"declared but absent from disk: {sorted(declared - on_disk)}"
    )


def test_the_bundle_covers_every_published_document():
    """The four documents a reader is being handed. Each must exist and be listed."""
    expected = {"README.md", "docs/design.md", "content/linkedin-post.md",
                "content/linkedin-article.md", "content/medium-post.md"}
    declared = {rel for rel, _ in DOCUMENTS}
    assert declared == expected, sorted(declared ^ expected)
    for rel, _ in DOCUMENTS:
        assert (REPO_ROOT / rel).exists(), f"the bundle lists {rel}, which does not exist"


def test_every_artifact_body_is_reproduced_in_full_not_excerpted():
    """The appendix claims the files verbatim. Spot-check the last line of each, which
    is what a truncating bug drops first."""
    md = build_markdown()
    for name, _ in ARTIFACTS:
        text = (METADATA_DIR / name).read_text(encoding="utf-8").rstrip()
        last = text.splitlines()[-1].strip()
        assert last and last in md, (
            f"the bundle's copy of {name} does not reach its final line: {last!r}"
        )


def test_every_figure_in_the_bundle_resolves_from_the_docs_directory():
    """The bundle is written into docs/, so `diagrams/x.svg` must resolve from there.

    Rewriting the two different source conventions (`docs/...` from the README,
    `../docs/...` from the article) is the step that breaks silently: Chrome prints a
    missing image as blank space, and a blank space reads as a layout choice.
    """
    md = build_markdown()
    embeds = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", md)
    assert len(embeds) >= 4, f"expected the figures from both documents, found {embeds}"
    for rel in embeds:
        assert not rel.startswith(("..", "docs/")), (
            f"{rel} will not resolve from docs/, where the bundle is written"
        )
        assert (OUT_MD.parent / rel).exists(), f"the bundle embeds {rel}, which is missing"


def test_the_bundle_on_disk_is_current():
    """Committed output has to match what the builder produces, or the PDF beside it is
    a render of a document nobody can regenerate."""
    assert OUT_MD.exists(), "run: python docs/build_bundle.py"
    assert OUT_MD.read_text(encoding="utf-8") == build_markdown(), (
        "docs/semantic-layer-complete.md is stale; re-run python docs/build_bundle.py"
    )


def test_the_bundle_is_deterministic():
    """No timestamp, no ordering wobble -- two builds must be byte-identical."""
    assert build_markdown() == build_markdown()
    assert not re.search(r"\b20\d\d-\d\d-\d\dT\d\d:", build_markdown()), \
        "a timestamp reached the bundle; re-running it would show a spurious diff"


def _headings(md: str, level: int) -> list[str]:
    """ATX headings at `level`, ignoring fenced code.

    The fence tracking is the point: the YAML and JSON artifacts are full of `# comment`
    lines, and a naive scan counts 35 of them as H1s. `fenced_code` protects them in the
    render, so a test that does not protect them too is testing its own bug.
    """
    out, in_fence = [], False
    for ln in md.splitlines():
        if ln.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence and re.match(rf"^#{{{level}}} \S", ln):
            out.append(ln)
    return out


def test_one_heading_hierarchy_across_the_bundle():
    """Exactly one H1 per part plus the cover. A stray source H1 would restart the
    document structure mid-bundle and break every PDF outline and bookmark."""
    h1s = _headings(build_markdown(), 1)
    assert len(h1s) == len(DOCUMENTS) + 2, h1s   # cover + 4 parts + appendix
    assert h1s[0].startswith("# Building a Semantic Layer")
    for i, ln in enumerate(h1s[1:], start=1):
        assert ln.startswith(f"# Part {i} — "), ln
