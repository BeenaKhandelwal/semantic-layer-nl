"""Split `content/medium-post.md` into the two artifacts publishing actually needs.

The post is deliberately self-contained: prose, excerpts, real output, and the whole
1,000-plus-line file in one fence. That is right for a reader who wants one document and
wrong for the person pressing publish, who needs the copy in one hand and the code in the
other.

So this generates, from that one source:

    content/medium-kit.md   the article as it will be published -- the complete-file fence
      -> .pdf               replaced by a pointer -- plus a cover sheet and the publishing
                            checklist bound in behind it
    content/medium-code.md  the companion file on its own, with its sha256
      -> .pdf

Neither is hand-written. `content/medium-post.md` stays the single source of truth, which
is what keeps `tests/test_content.py`'s byte-identity check meaningful: the code that ships
is the code `tests/test_standalone.py` runs, and everything else is derived from it.

Usage:
    python content/build_medium_kit.py          # write both .md files and both PDFs
    python content/build_medium_kit.py --md-only
    python content/build_medium_kit.py --check  # exit 1 if either .md on disk is stale
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.semantic.constants import AS_OF_DATE, REPO_ROOT  # noqa: E402

POST = REPO_ROOT / "content" / "medium-post.md"
CHECKLIST = REPO_ROOT / "content" / "medium-publishing-checklist.md"
STANDALONE = REPO_ROOT / "standalone" / "semantic_layer_demo.py"

KIT_MD = REPO_ROOT / "content" / "medium-kit.md"
CODE_MD = REPO_ROOT / "content" / "medium-code.md"

PAGE_BREAK = '<div style="page-break-before: always;"></div>'

# The heading whose fence gets lifted out. Named once; asserted to exist.
COMPLETE_FILE_HEADING = "## The complete file"


def _sha12(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def _lift_the_complete_file(post: str) -> str:
    """Replace the complete-file section's body with a pointer to the companion.

    Structural, not a string swap: find the heading, find the fence that follows it, and
    check the fence really is the big one. If the post is restructured this raises rather
    than silently shipping a kit with the code still in it -- or worse, with the pointer
    dropped into the wrong section.
    """
    start = post.index(COMPLETE_FILE_HEADING)
    fence_open = post.index("```python", start)
    fence_close = post.index("\n```", fence_open) + len("\n```")
    fence = post[fence_open:fence_close]
    lines = len(fence.splitlines())
    assert lines > 200, (
        f"the fence under {COMPLETE_FILE_HEADING!r} is only {lines} lines; the kit builder "
        f"is lifting the wrong block"
    )

    replacement = (
        f"{COMPLETE_FILE_HEADING}\n\n"
        f"The whole file is {len(STANDALONE.read_text(encoding='utf-8').splitlines())} "
        f"lines, so it ships beside this document rather than inside it:\n\n"
        f"- **`medium-code.pdf`** — the same file, printed, for reading.\n"
        f"- **`standalone/semantic_layer_demo.py`** — the file itself, sha256 "
        f"`{_sha12(STANDALONE)}`. This is the copy to publish as a Gist; no PDF is a\n"
        f"  reliable place to copy code from.\n\n"
        f"Nothing else is needed to run it — no repository, no data files, no credentials:\n\n"
        f"```bash\npip install duckdb pyyaml\npython semantic_layer_demo.py\n```\n\n"
    )
    return post[:start] + replacement + post[fence_close:].lstrip("\n")


def _cover(post_lines: int) -> str:
    title = POST.read_text(encoding="utf-8").splitlines()[0].lstrip("# ").strip()
    return (
        "# Medium publication kit\n\n"
        f"**{title}**\n\n"
        "Everything needed to publish, in reading order. Generated from "
        "`content/medium-post.md` by `content/build_medium_kit.py` — regenerate rather "
        "than edit, or the copy here stops matching the copy under test.\n\n"
        "## What is in this document\n\n"
        "- **Part 1 — The article, as it will be published.** Prose, code excerpts, real "
        "console output, and both figures. The one thing lifted out is the complete "
        "source file, which is too long to sit inside a document meant for editing.\n"
        "- **Part 2 — The publishing checklist.** Title and subtitle slots, tags, which "
        "figure goes where, the canonical-URL decision, sequencing against the two "
        "LinkedIn pieces, and what to cut if it runs long.\n\n"
        "## The companion file\n\n"
        f"`medium-code.pdf` carries the complete runnable file — "
        f"{len(STANDALONE.read_text(encoding='utf-8').splitlines())} lines, sha256 "
        f"`{_sha12(STANDALONE)}`. Publish it as a Gist and link it from the article; PDFs "
        "and copy-paste do not mix.\n\n"
        "## Before publishing\n\n"
        "Every figure in Part 1 is measured against a warehouse built from the committed "
        f"CSVs at a frozen as-of date of **{AS_OF_DATE.isoformat()}**. The console output "
        "is a real run, spliced in by the build, not transcribed. To confirm both before "
        "you publish:\n\n"
        "```bash\n"
        "python content/build_medium_post.py --check\n"
        "python content/build_medium_kit.py --check\n"
        "python -m pytest tests/test_content.py tests/test_standalone.py -q\n"
        "```\n\n"
        f"*Article source: `content/medium-post.md` ({post_lines} lines).*\n"
    )


def build_kit() -> str:
    post = POST.read_text(encoding="utf-8")
    body = _lift_the_complete_file(post)

    # The post's own H1/H2 are the Medium title and subtitle -- they must survive into the
    # kit exactly, because Part 1 is what gets pasted. So the cover owns the document H1
    # and Part 1 keeps the article's, one level down.
    body = re.sub(r"^# ", "## TITLE — ", body, count=1, flags=re.M)
    body = re.sub(r"^## (?!TITLE)", "### SUBTITLE — ", body, count=1, flags=re.M)

    checklist = CHECKLIST.read_text(encoding="utf-8")
    checklist = re.sub(r"^# .*$", "", checklist, count=1, flags=re.M).lstrip("\n")

    return (
        _cover(len(post.splitlines()))
        + f"\n{PAGE_BREAK}\n\n# Part 1 — The article, as it will be published\n\n"
        + "*The two lines marked TITLE and SUBTITLE go in Medium's title and subtitle "
        "slots, not in the body.*\n\n"
        + body.rstrip()
        + f"\n\n{PAGE_BREAK}\n\n# Part 2 — Publishing checklist\n\n"
        + checklist.rstrip()
        + "\n"
    )


def build_code() -> str:
    source = STANDALONE.read_text(encoding="utf-8")
    return (
        "# Companion file — `semantic_layer_demo.py`\n\n"
        f"**{len(source.splitlines())} lines · sha256 `{_sha12(STANDALONE)}` · "
        "runs on `pip install duckdb pyyaml`**\n\n"
        "This is the complete file the article walks through, printed for reading. It is "
        "byte-identical to `standalone/semantic_layer_demo.py`, which the project's test "
        "suite executes — `tests/test_standalone.py` asserts the numbers it prints against "
        "the same warehouse the full pipeline uses.\n\n"
        "To run it, copy the file rather than this PDF: a PDF inserts its own line breaks "
        "and drops the leading whitespace Python depends on.\n\n"
        "---\n\n"
        f"```python\n{source.rstrip()}\n```\n"
    )


TARGETS = ((KIT_MD, build_kit), (CODE_MD, build_code))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--md-only", action="store_true",
                    help="write the markdown but skip the PDFs (no browser required)")
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if either markdown on disk is not what this would write")
    args = ap.parse_args()

    if args.check:
        for path, builder in TARGETS:
            current = path.read_text(encoding="utf-8") if path.exists() else ""
            if current != builder():
                raise SystemExit(
                    f"{path.name} is stale; run: python {Path(__file__).name}")
        print(f"{KIT_MD.name} and {CODE_MD.name} are current")
        return

    for path, builder in TARGETS:
        text = builder()
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"{path.relative_to(REPO_ROOT)}  ({len(text.splitlines())} lines, "
              f"{len(text) / 1024:.0f} KB)")

    if args.md_only:
        return

    from docs.md2pdf import to_pdf
    for path, _ in TARGETS:
        pdf = to_pdf(path, path.with_suffix(".pdf"))
        print(f"{pdf.relative_to(REPO_ROOT)}  ({pdf.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
