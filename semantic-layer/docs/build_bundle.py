"""Assemble every document and every metadata artifact into one printable bundle.

Why a build script rather than a hand-maintained file: "everything" is a claim that
rots. A concatenation done by hand quietly loses whichever artifact was added last, and
the missing one is invisible in a 70-page PDF. Here the section list is declared once,
`tests/test_bundle.py` asserts it covers all nine artifacts and all four documents, and
the bundle is regenerated rather than edited.

Two details that are not cosmetic:

* Image paths. README embeds `docs/diagrams/x.svg` (relative to the repo root); the
  article embeds `../docs/diagrams/x.svg` (relative to `content/`). The bundle is written
  into `docs/`, so both are rewritten to `diagrams/x.svg` or the figures silently fail to
  load and print as empty space.
* Heading levels. Each source owns its own `## 1.` numbering, so the source's leading H1
  is lifted into a `# Part N` title and `00_kpi_contract.md`'s headings are demoted one
  level, keeping one heading hierarchy across the whole bundle.

Deterministic: no timestamp is written. The only date in the output is the project's
frozen as-of date.

Usage:
    python docs/build_bundle.py            # writes docs/semantic-layer-complete.md + .pdf
    python docs/build_bundle.py --md-only  # skip the PDF (no browser needed)
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.semantic.constants import AS_OF_DATE, METADATA_DIR, REPO_ROOT  # noqa: E402

OUT_MD = REPO_ROOT / "docs" / "semantic-layer-complete.md"
OUT_PDF = REPO_ROOT / "docs" / "semantic-layer-complete.pdf"

# The documents, in reading order. `title` overrides the source's own H1 where the
# source's H1 is a filename-ish label rather than a part title.
DOCUMENTS = [
    ("README.md", "The Implementation Guide"),
    ("docs/design.md", "The Design Spec and Acceptance Criteria"),
    ("content/linkedin-post.md", "The LinkedIn Post"),
    ("content/linkedin-article.md", "The LinkedIn Article"),
    ("content/medium-post.md", "The Medium Post, With Complete Executable Code"),
]

# The nine artifacts, in phase order, with the fence language each needs.
ARTIFACTS = [
    ("00_kpi_contract.md", "markdown"),
    ("01_technical_metadata.json", "json"),
    ("02_standardized_metadata.json", "json"),
    ("03_glossary.yml", "yaml"),
    ("03_column_bindings.yml", "yaml"),
    ("04_process_model.yml", "yaml"),
    ("05_semantic_model.yml", "yaml"),
    ("06_dq_rules.yml", "yaml"),
    ("07_catalog_asset.json", "json"),
]

PAGE_BREAK = '<div style="page-break-before: always;"></div>'


def _rewrite_image_paths(text: str) -> str:
    """Make every embedded figure resolve from `docs/`, where the bundle is written."""
    text = text.replace("](../docs/diagrams/", "](diagrams/")
    text = text.replace("](docs/diagrams/", "](diagrams/")
    # The same rewrite for the inline links that sit under each figure as captions.
    text = text.replace("(`docs/diagrams/", "(`diagrams/")
    return text


def _split_h1(text: str) -> tuple[str | None, str]:
    """Lift a leading `# Title` out of the body so it can become the part heading."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("# "):
            return line[2:].strip(), "\n".join(lines[:i] + lines[i + 1:]).lstrip("\n")
        if line.strip() and not line.startswith(("<!--", "---")):
            break
    return None, text


def _demote_headings(text: str) -> str:
    """Add one `#` to every ATX heading, so a nested document keeps one hierarchy."""
    return re.sub(r"^(#{1,5}) ", r"#\1 ", text, flags=re.MULTILINE)


def _sha12(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def build_markdown() -> str:
    parts: list[str] = []

    parts.append(
        f"# Building a Semantic Layer for Natural-Language Querying\n\n"
        f"**Complete bundle — implementation guide, design spec, published write-ups, "
        f"and all nine metadata artifacts verbatim.**\n\n"
        f"All figures in this document are measured against a warehouse built from the "
        f"committed CSVs at a frozen as-of date of **{AS_OF_DATE.isoformat()}**, so every "
        f"number here is reproducible by running `python verify_acceptance.py`.\n\n"
        f"## Contents\n\n"
        + "\n".join(
            f"- **Part {i}** — {t or Path(p).name}  (`{p}`)"
            for i, (p, t) in enumerate(DOCUMENTS, start=1)
        )
        + f"\n- **Part {len(DOCUMENTS) + 1}** — Appendix: the nine metadata artifacts, "
        f"in full\n"
    )

    for i, (rel, override) in enumerate(DOCUMENTS, start=1):
        src = REPO_ROOT / rel
        own_title, body = _split_h1(src.read_text(encoding="utf-8"))
        title = override or own_title or Path(rel).stem
        parts.append(
            f"{PAGE_BREAK}\n\n# Part {i} — {title}\n\n"
            f"*Source: `{rel}`*\n\n" + _rewrite_image_paths(body)
        )

    n = len(DOCUMENTS) + 1
    appendix = [
        f"{PAGE_BREAK}\n\n# Part {n} — Appendix: The Nine Metadata Artifacts\n\n"
        "Reproduced in full, in phase order. Each is the file the pipeline actually "
        "reads — not an excerpt rewritten for the page. The SHA-256 prefix beside each "
        "one is of the committed bytes, so a reader can confirm the copy they cloned is "
        "the copy quoted here.\n"
    ]
    for j, (name, lang) in enumerate(ARTIFACTS, start=1):
        path = METADATA_DIR / name
        text = path.read_text(encoding="utf-8")
        header = (
            f"## {n}.{j} `{name}`\n\n"
            f"*{len(text.splitlines())} lines · sha256 `{_sha12(path)}`*\n\n"
        )
        if lang == "markdown":
            appendix.append(header + _demote_headings(text))
        else:
            appendix.append(header + f"```{lang}\n{text.rstrip()}\n```\n")
    parts.append("\n\n".join(appendix))

    return "\n\n".join(parts).rstrip() + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--md-only", action="store_true",
                    help="write the markdown but skip the PDF (no browser required)")
    args = ap.parse_args()

    md = build_markdown()
    OUT_MD.write_text(md, encoding="utf-8", newline="\n")
    print(f"{OUT_MD.relative_to(REPO_ROOT)}  ({len(md.splitlines())} lines, "
          f"{len(md) / 1024:.0f} KB)")

    if args.md_only:
        return

    from docs.md2pdf import to_pdf
    to_pdf(OUT_MD, OUT_PDF)
    print(f"{OUT_PDF.relative_to(REPO_ROOT)}  ({OUT_PDF.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
