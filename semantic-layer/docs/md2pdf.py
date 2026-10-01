"""Markdown -> styled HTML -> PDF, using headless Chrome as the print engine.

Why Chrome rather than a Python PDF library: this repo's documents are mostly tables,
and every pure-Python markdown-to-PDF path available here either drops table borders
(reportlab, by hand) or needs GTK native libraries that are not installed (WeasyPrint
imports but cannot load `libgobject-2.0-0`). Chrome renders the same HTML a reader would
see in a browser, so a wide table degrades by wrapping rather than by silently losing
columns.

Deterministic by construction: no timestamp is written into the output, so re-running on
an unchanged source produces an equivalent PDF.

Usage:
    python docs/md2pdf.py docs/design.md
    python docs/md2pdf.py docs/design.md --out docs/design.pdf
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown

# Landscape-ish A4 with narrow margins: the design doc has 7-column tables that lose
# their shape at portrait width.
CSS = """
@page { size: A4; margin: 14mm 12mm 16mm 12mm; }
body {
  font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
  font-size: 9.6pt; line-height: 1.45; color: #1a1a1a; margin: 0;
}
h1 { font-size: 20pt; margin: 0 0 4pt; color: #0f2942;
     border-bottom: 2.5pt solid #0f2942; padding-bottom: 5pt; }
h2 { font-size: 14pt; margin: 20pt 0 6pt; color: #0f2942;
     border-bottom: 0.6pt solid #c3ccd6; padding-bottom: 3pt;
     page-break-after: avoid; }
h3 { font-size: 11.4pt; margin: 14pt 0 4pt; color: #1c3f5f;
     page-break-after: avoid; }
h4 { font-size: 10pt; margin: 11pt 0 3pt; color: #1c3f5f; }
p { margin: 0 0 6pt; }
ul, ol { margin: 0 0 7pt; padding-left: 17pt; }
li { margin-bottom: 2.5pt; }
code {
  font-family: "Cascadia Mono", Consolas, "Courier New", monospace;
  font-size: 8.6pt; background: #f1f4f7; padding: 0.6pt 3pt;
  border-radius: 2pt; color: #7d2000;
}
pre {
  background: #f7f9fb; border: 0.6pt solid #d6dee6; border-left: 2.5pt solid #0f2942;
  padding: 7pt 9pt; overflow-x: auto; page-break-inside: avoid; margin: 0 0 9pt;
}
pre code {
  background: none; padding: 0; color: #16324a; font-size: 8.2pt; line-height: 1.36;
  white-space: pre-wrap; word-break: break-word;
}
/* Without this, an intrinsically-sized SVG prints at its own width -- the 21in wide
   diagrams overflowed A4 and Chrome silently CLIPPED the right third of the figure,
   which is the half that shows how the metadata gets used. Scaled-to-fit is small but
   whole; clipped is a figure that misrepresents itself. The prose beside each one
   points at the full-resolution file for anyone who needs to read the labels. */
img {
  max-width: 100%; height: auto; display: block;
  margin: 10pt auto 4pt; page-break-inside: avoid;
}
table {
  border-collapse: collapse; width: 100%; margin: 0 0 10pt;
  font-size: 8.5pt; page-break-inside: avoid;
}
/* overflow-wrap, NOT word-break. `word-break: break-word` is defined as
   `overflow-wrap: anywhere`, which lets a word break even when the column could have
   been widened to fit it -- so Chrome's table layout sized a column to one character
   and printed "provena / nce". `overflow-wrap: break-word` keeps the safety net for
   identifiers genuinely too long for any column, but sizes columns from whole words. */
th, td {
  border: 0.5pt solid #c3ccd6; padding: 3.6pt 5pt; text-align: left;
  vertical-align: top; overflow-wrap: break-word;
}
th { background: #e8edf2; font-weight: 600; color: #0f2942; }
tr:nth-child(even) td { background: #fafbfc; }
blockquote {
  margin: 0 0 8pt; padding: 5pt 10pt; border-left: 2.5pt solid #7aa0c0;
  background: #f5f8fb; color: #26445e;
}
hr { border: none; border-top: 0.6pt solid #d6dee6; margin: 14pt 0; }
strong { color: #0f2942; }
a { color: #1c5f9e; text-decoration: none; }
"""

CHROME_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)


def find_chrome() -> str:
    """Locate a Chromium-family browser to print with, or exit with a usable message."""
    for name in ("chrome", "msedge", "chromium"):
        found = shutil.which(name)
        if found:
            return found
    for path in CHROME_CANDIDATES:
        if Path(path).exists():
            return path
    sys.exit(
        "No Chromium-family browser found to print with. Tried PATH (chrome, msedge, "
        "chromium) and the standard Windows install locations."
    )


def render_html(md_path: Path) -> str:
    """Convert markdown to a standalone HTML document with the print stylesheet inlined."""
    text = md_path.read_text(encoding="utf-8")
    body = markdown.markdown(
        text,
        extensions=["tables", "fenced_code", "sane_lists", "attr_list", "toc"],
    )
    title = md_path.stem.replace("_", " ").replace("-", " ").title()
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<title>{title}</title><style>{CSS}</style></head>"
        f"<body>\n{body}\n</body></html>\n"
    )


def to_pdf(md_path: Path, out_path: Path) -> Path:
    """Render `md_path` to `out_path`. Returns the output path."""
    chrome = find_chrome()
    html = render_html(md_path)

    # Chrome will not print a file it cannot read from disk, and it resolves relative
    # asset paths against the HTML's own directory -- so the temp file goes next to the
    # source document, not into %TEMP%, or images in docs/ would fail to load.
    with tempfile.NamedTemporaryFile(
        "w", suffix=".html", dir=md_path.parent, delete=False, encoding="utf-8"
    ) as fh:
        fh.write(html)
        tmp_html = Path(fh.name)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            [
                chrome,
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                "--no-pdf-header-footer",
                "--run-all-compositor-stages-before-draw",
                "--virtual-time-budget=10000",
                f"--print-to-pdf={out_path}",
                tmp_html.as_uri(),
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
    finally:
        tmp_html.unlink(missing_ok=True)

    # Chrome's exit code is not a reliable success signal in headless print mode; the
    # existence of a non-trivial PDF is.
    if not out_path.exists() or out_path.stat().st_size < 1000:
        sys.exit(
            f"Chrome did not produce a usable PDF (rc={result.returncode}).\n"
            f"stderr: {result.stderr[:2000]}"
        )
    return out_path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("markdown", type=Path, help="source .md file")
    ap.add_argument("--out", type=Path, default=None, help="output .pdf (default: alongside)")
    args = ap.parse_args()

    md_path = args.markdown.resolve()
    if not md_path.exists():
        sys.exit(f"not found: {md_path}")
    out = (args.out or md_path.with_suffix(".pdf")).resolve()

    to_pdf(md_path, out)
    kb = out.stat().st_size / 1024
    print(f"{md_path.name} -> {out}  ({kb:.0f} KB)")


if __name__ == "__main__":
    main()
