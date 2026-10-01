"""Render the metadata provenance map: where each artifact COMES FROM, and how it is USED.

The companion diagram (`render_dataflow.py`) answers "which stage reads which artifact
when a question arrives". It says nothing about where those artifacts came from, which is
the question everyone asks second and every metadata programme underestimates:

    "Can't we just harvest this from the source system?"

The honest answer this picture makes visible: **one of the nine artifacts is
machine-harvestable. One.** `01_technical_metadata.json` comes out of SAP DDIC via SE11 /
SE16. Everything else is either DERIVED from an earlier artifact plus the data, or
AUTHORED by a named human who had to decide something no system knows -- what "on-time"
means, what a standard inspection takes, what completeness threshold is tolerable.

That is the load-bearing insight for anyone planning this work, because it sets where the
effort and the calendar time actually go. A crawler gets you column names and types. It
cannot get you grain, exclusions, or an approved definition, and those are the fields that
decide whether the answer is right.

The three provenance kinds, which the diagram colours:

* HARVESTED -- extracted from a running system by a repeatable query. Cheap, automatable,
  and only ever the raw material.
* DERIVED   -- computed from earlier artifacts plus the data. Cheap to keep current,
  because the inputs are themselves versioned artifacts.
* AUTHORED  -- decided by a person with a name and accountability. Expensive, slow, and
  the part that makes natural-language answers defensible.

Layout: sources (left) -> collection method -> artifact (P0..P7) -> when it is consumed
(right). The right-hand band ties this diagram back to the dataflow one, so the two
together read as one story: collected here, used there.

Everything is declared as data (`SOURCES`, `ARTIFACTS`, `EDGES`) and drawn from the
declaration, so `tests/test_diagram.py` can verify the claims against the real artifact
files. An edge claiming P2 derives from P1 must be a claim the artifact's own lineage
supports, or the suite fails rather than shipping a plausible fiction.

Determinism matches render_dataflow.py: no wall-clock, no randomness, pinned hashsalt.

    python docs/diagrams/render_sources.py --write    # regenerate SVG + PNG
    python docs/diagrams/render_sources.py --check    # fail if committed output is stale
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["svg.hashsalt"] = "semantic-layer-nl"
matplotlib.rcParams["svg.fonttype"] = "path"

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle  # noqa: E402

HERE = Path(__file__).resolve().parent
SVG_PATH = HERE / "metadata_sources.svg"
PNG_PATH = HERE / "metadata_sources.png"

# --------------------------------------------------------------------------------------
# palette -- three provenance kinds, one colour each, used consistently everywhere
# --------------------------------------------------------------------------------------

KIND = {
    "harvested": {"fill": "#e3f0fb", "edge": "#1f6fb2", "text": "#14486f",
                  "label": "HARVESTED from a system"},
    "derived":   {"fill": "#e8f5e9", "edge": "#2e7d32", "text": "#1b5e20",
                  "label": "DERIVED from earlier artifacts + data"},
    "authored":  {"fill": "#fdecea", "edge": "#c0392b", "text": "#8c2318",
                  "label": "AUTHORED by a named human"},
}

INK = "#1a1a1a"
MUTED = "#5a6470"

# --------------------------------------------------------------------------------------
# the graph, as data
# --------------------------------------------------------------------------------------

# `probe` is a string that must occur in the named artifact, so the drift test can prove
# the source claim is the artifact's own claim and not the diagram's invention.
SOURCES = [
    {"key": "ddic", "label": "SAP DDIC",
     "detail": "SE11 / SE16 metadata query\nSAP ERP 6.0 EHP8\n10 tables, 20 fields",
     "kind": "harvested"},
    {"key": "txn", "label": "SAP transactional data",
     "detail": "SD, PP, QM, MM, LE-SHP, TM\nvia BW extractors (2LIS_*)\n-> data lake bronze",
     "kind": "harvested"},
    {"key": "warehouse", "label": "The built warehouse",
     "detail": "profiling + schema introspection\nbindings checked against\nreal columns at build time",
     "kind": "derived"},
    {"key": "artifacts", "label": "Earlier artifacts",
     "detail": "metadata deriving from\nmetadata -- P2 from P1,\nP5 from P2/P3/P4",
     "kind": "derived"},
    {"key": "business", "label": "Business + governance",
     "detail": "CDO, Data Governance Council,\nVP Supply Chain, Manufacturing\nExcellence, Data Engineering",
     "kind": "authored"},
]

ARTIFACTS = [
    {"file": "00_kpi_contract.md", "p": "P0", "kind": "authored",
     "how": "signed definition workshop",
     "gives": "what the number must mean",
     "use": "contract", "owner": "VP Supply Chain"},
    {"file": "01_technical_metadata.json", "p": "P1", "kind": "harvested",
     "how": "SE11 / SE16 extract",
     "gives": "tables, fields, domains, types",
     "use": "build", "owner": "SAP Basis / Data Eng"},
    {"file": "02_standardized_metadata.json", "p": "P2", "kind": "derived",
     "how": "P1 + raw data + staging SQL",
     "gives": "canonical names, DECLARED GRAIN, join paths",
     "use": "build", "owner": "Data Engineering"},
    {"file": "03_glossary.yml", "p": "P3", "kind": "authored",
     "how": "governance council ratifies",
     "gives": "terms, synonyms, definitions",
     "use": "query", "owner": "Chief Data Officer"},
    {"file": "03_column_bindings.yml", "p": "P3", "kind": "derived",
     "how": "term -> column, checked vs schema",
     "gives": "physical binding for each term",
     "use": "query", "owner": "Data Engineering Team"},
    {"file": "04_process_model.yml", "p": "P4", "kind": "authored",
     "how": "ops sets the standards",
     "gives": "12 phases, standard durations, attribution rule",
     "use": "query", "owner": "VP Supply Chain Ops"},
    {"file": "05_semantic_model.yml", "p": "P5", "kind": "derived",
     "how": "P2 grain + P3 words + P4 phases",
     "gives": "metrics, exclusions, approval_state",
     "use": "query", "owner": "VP Supply Chain"},
    {"file": "06_dq_rules.yml", "p": "P6", "kind": "authored",
     "how": "thresholds are a judgement",
     "gives": "6 rules bound to metrics",
     "use": "query", "owner": "Data Governance"},
    {"file": "07_catalog_asset.json", "p": "P7", "kind": "derived",
     "how": "P5 + P6 + governance fields",
     "gives": "owner, 11-step lineage, certification",
     "use": "query", "owner": "Data Governance"},
]

# source -> artifact. `probe` must appear in the artifact file (drift test).
EDGES = [
    {"src": "business", "file": "00_kpi_contract.md", "probe": "VP Supply Chain"},
    {"src": "ddic", "file": "01_technical_metadata.json", "probe": "SE11 / SE16"},
    {"src": "txn", "file": "01_technical_metadata.json", "probe": "2LIS_"},
    {"src": "artifacts", "file": "02_standardized_metadata.json",
     "probe": "01_technical_metadata.json"},
    {"src": "txn", "file": "02_standardized_metadata.json", "probe": "data/*_raw.csv"},
    {"src": "business", "file": "03_glossary.yml", "probe": "Data Governance Council"},
    {"src": "warehouse", "file": "03_column_bindings.yml",
     "probe": "validated at build time"},
    {"src": "artifacts", "file": "03_column_bindings.yml", "probe": "fact_order_delivery"},
    {"src": "business", "file": "04_process_model.yml", "probe": "Manufacturing Excellence"},
    {"src": "artifacts", "file": "05_semantic_model.yml", "probe": "fact_order_delivery"},
    {"src": "business", "file": "05_semantic_model.yml", "probe": "approval_state"},
    {"src": "business", "file": "06_dq_rules.yml", "probe": "threshold"},
    {"src": "artifacts", "file": "07_catalog_asset.json", "probe": "on_time_delivery_pct"},
]

# Right-hand band: how the artifact is used when a question arrives. Mirrors
# render_dataflow.py's EDGES so the two diagrams cannot disagree; the drift test
# cross-checks them.
USE = {
    "contract": {"label": "ACCEPTANCE ORACLE",
                 "detail": "no stage reads it at runtime;\nit is what the answer is judged against"},
    "build": {"label": "BUILD TIME",
              "detail": "consumed once by sql/02_staging_model.sql\nand the warehouse build -- NOT per question"},
    "query": {"label": "QUERY TIME",
              "detail": "read on every question by\nretriever / validator / compiler / provenance"},
}

ANNOTATIONS = [
    "Exactly ONE artifact is machine-harvestable (P1). A crawler gets you types, never grain.",
    "The AUTHORED artifacts are where the calendar time goes -- and where trust comes from.",
    "P1 and P2 are consumed at BUILD time. SAP DDIC is not a live dependency of every question.",
    "Every artifact carries an owner, so a wrong number has someone to ask, not just a table to blame.",
]

# --------------------------------------------------------------------------------------
# layout
# --------------------------------------------------------------------------------------

FIG_W, FIG_H = 21.0, 14.4

SRC_X, SRC_W, SRC_H = 0.30, 3.55, 1.06
ART_X, ART_W = 5.35, 8.90
USE_X, USE_W = 15.55, 5.10

# Header bars carry two lines (title + what the column means). A single-line bar put the
# sub-label right-aligned in the same strip, where it collided with the title in both
# narrow columns -- visible immediately in the rendered PNG and invisible in the code.
BAR_Y, BAR_H = 12.40, 0.54

ROW_TOP = 12.30
ROW_H = 1.08
ROW_GAP = 0.115

# The annotation strip is anchored from the bottom, so the row block and the source
# column both have to clear it. Checked arithmetic rather than eyeballed: nine rows at
# ROW_H + ROW_GAP from ROW_TOP land at 1.66, and the strip tops out at 1.44.
ANN_Y, ANN_H = 0.24, 1.32


def _row_y(i: int) -> float:
    return ROW_TOP - i * (ROW_H + ROW_GAP)


def _src_y(i: int) -> float:
    """Sources are fewer and taller; spread them over the artifact column's span.

    Spread over the span less a reserve, so the last (tallest, three-line) source box
    keeps clear of the annotation strip instead of overlapping it.
    """
    span = (len(ARTIFACTS) - 1) * (ROW_H + ROW_GAP) - 0.60
    step = span / (len(SOURCES) - 1)
    return ROW_TOP - i * step - 0.16


def layout_boxes() -> dict[str, dict[str, float]]:
    """Every opaque rectangle the figure draws, as x / y / w / h.

    Exists so the overlap test asserts on the numbers the renderer actually draws with,
    rather than re-deriving the layout and drifting from it. Three of the five defects in
    this diagram were collisions that only the rendered PNG revealed; this is the subset a
    test can hold. The use-band and legend are omitted deliberately -- they occupy columns
    nothing else is drawn in.
    """
    out: dict[str, dict[str, float]] = {}
    for i, s in enumerate(SOURCES):
        out[f"source:{s['key']}"] = {
            "x": SRC_X, "y": _src_y(i) - SRC_H, "w": SRC_W, "h": SRC_H}
    for i, a in enumerate(ARTIFACTS):
        out[f"artifact:{a['file']}"] = {
            "x": ART_X, "y": _row_y(i) - ROW_H, "w": ART_W, "h": ROW_H}
    out["annotations"] = {
        "x": SRC_X - 0.16, "y": ANN_Y, "w": FIG_W - 0.94, "h": ANN_H}
    return out


def annotation_line_y(i: int) -> float:
    """Baseline of the i-th annotation line. The fourth line rendered below the box floor
    at ANN_H = 1.20; the test that pins this is cheaper than reading the PNG again."""
    return ANN_Y + ANN_H - 0.53 - i * 0.24


def _box(ax, x, y, w, h, kind, zorder=2, lw=1.5):
    c = KIND[kind]
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.045,rounding_size=0.10",
        facecolor=c["fill"], edgecolor=c["edge"], linewidth=lw, zorder=zorder))
    return c


def _build_figure():
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
    ax.set_xlim(0, FIG_W)
    ax.set_ylim(0, FIG_H)
    ax.axis("off")

    # ---- title -----------------------------------------------------------------
    ax.text(0.30, 13.86, "Where each metadata artifact COMES FROM, and how it is USED",
            fontsize=21, fontweight="bold", color="#0f2942", va="center")
    ax.text(0.30, 13.44,
            "Nine artifacts, three kinds of provenance. Only ONE can be harvested from a "
            "source system -- the rest are derived or decided.",
            fontsize=11.6, color=MUTED, va="center")

    # ---- legend ----------------------------------------------------------------
    lx = 0.34
    for kind in ("harvested", "derived", "authored"):
        c = KIND[kind]
        ax.add_patch(FancyBboxPatch(
            (lx, 13.04), 0.34, 0.26,
            boxstyle="round,pad=0.02,rounding_size=0.05",
            facecolor=c["fill"], edgecolor=c["edge"], linewidth=1.4, zorder=3))
        n = sum(1 for a in ARTIFACTS if a["kind"] == kind)
        ax.text(lx + 0.46, 13.17, f"{c['label']}  ({n})",
                fontsize=10.4, color=c["text"], fontweight="bold", va="center", zorder=3)
        lx += 6.15

    # ---- column headers --------------------------------------------------------
    for x, w, head, sub in (
        (SRC_X, SRC_W, "1.  SOURCE", "where the content originates"),
        (ART_X, ART_W, "2.  COLLECTION  ->  ARTIFACT", "how it is captured, and what it adds"),
        (USE_X, USE_W, "3.  HOW IT ANSWERS A QUESTION", "when the pipeline consumes it"),
    ):
        ax.add_patch(Rectangle((x - 0.16, BAR_Y), w + 0.34, BAR_H,
                               facecolor="#0f2942", edgecolor="none", zorder=2))
        ax.text(x - 0.04, BAR_Y + BAR_H - 0.17, head, fontsize=11.2, fontweight="bold",
                color="white", va="center", zorder=3)
        ax.text(x - 0.04, BAR_Y + 0.16, sub, fontsize=9.0, color="#c9d6e4",
                va="center", zorder=3)

    # ---- source boxes ----------------------------------------------------------
    src_anchor = {}
    for i, s in enumerate(SOURCES):
        y = _src_y(i)
        h = SRC_H
        c = _box(ax, SRC_X, y - h, SRC_W, h, s["kind"])
        ax.text(SRC_X + 0.16, y - 0.23, s["label"], fontsize=11.0,
                fontweight="bold", color=c["text"], va="center", zorder=3)
        # Three detail lines centred on the box's lower two thirds; the first draft used a
        # 0.98-high box and the third line fell through the bottom edge.
        ax.text(SRC_X + 0.16, y - 0.68, s["detail"], fontsize=8.3,
                color=MUTED, va="center", linespacing=1.45, zorder=3)
        src_anchor[s["key"]] = (SRC_X + SRC_W + 0.05, y - h / 2)

    # ---- artifact rows ---------------------------------------------------------
    art_anchor_in, art_anchor_out = {}, {}
    for i, a in enumerate(ARTIFACTS):
        y = _row_y(i)
        c = _box(ax, ART_X, y - ROW_H, ART_W, ROW_H, a["kind"])

        # phase chip
        ax.add_patch(FancyBboxPatch(
            (ART_X + 0.12, y - 0.53), 0.60, 0.38,
            boxstyle="round,pad=0.02,rounding_size=0.06",
            facecolor=c["edge"], edgecolor="none", zorder=3))
        ax.text(ART_X + 0.42, y - 0.34, a["p"], fontsize=10.6, fontweight="bold",
                color="white", ha="center", va="center", zorder=4)

        ax.text(ART_X + 0.86, y - 0.29, a["file"], fontsize=11.0,
                fontweight="bold", color=INK, va="center", zorder=3,
                family="DejaVu Sans Mono")
        ax.text(ART_X + 0.86, y - 0.62, f"how:  {a['how']}", fontsize=8.8,
                color=c["text"], va="center", zorder=3)
        ax.text(ART_X + 0.86, y - 0.88, f"adds:  {a['gives']}", fontsize=8.8,
                color=MUTED, va="center", zorder=3)
        ax.text(ART_X + ART_W - 0.14, y - 0.29, a["owner"], fontsize=8.4,
                color=MUTED, va="center", ha="right", style="italic", zorder=3)

        art_anchor_in[a["file"]] = (ART_X - 0.05, y - ROW_H / 2)
        art_anchor_out[a["file"]] = (ART_X + ART_W + 0.05, y - ROW_H / 2)

    # ---- source -> artifact arrows --------------------------------------------
    for e in EDGES:
        x0, y0 = src_anchor[e["src"]]
        x1, y1 = art_anchor_in[e["file"]]
        kind = next(s["kind"] for s in SOURCES if s["key"] == e["src"])
        ax.add_patch(FancyArrowPatch(
            (x0, y0), (x1, y1),
            connectionstyle="arc3,rad=0.055",
            arrowstyle="-|>", mutation_scale=11,
            linewidth=1.15, color=KIND[kind]["edge"], alpha=0.55, zorder=1))

    # ---- use band --------------------------------------------------------------
    groups = {}
    for i, a in enumerate(ARTIFACTS):
        groups.setdefault(a["use"], []).append(i)

    band_style = {
        "contract": ("#fffdf5", "#d6c98a", "#7d6608"),
        "build": ("#f3f0fa", "#7e57c2", "#4527a0"),
        "query": ("#e8f5e9", "#2e7d32", "#1b5e20"),
    }
    for use, idxs in groups.items():
        top = _row_y(min(idxs))
        bot = _row_y(max(idxs)) - ROW_H
        fill, edge, text = band_style[use]
        ax.add_patch(FancyBboxPatch(
            (USE_X, bot), USE_W, top - bot,
            boxstyle="round,pad=0.05,rounding_size=0.10",
            facecolor=fill, edgecolor=edge, linewidth=1.7, zorder=2))
        ax.text(USE_X + 0.20, top - 0.30, USE[use]["label"], fontsize=11.4,
                fontweight="bold", color=text, va="center", zorder=3)
        ax.text(USE_X + 0.20, top - 0.72, USE[use]["detail"], fontsize=8.9,
                color=MUTED, va="center", linespacing=1.55, zorder=3)
        # arrows from each artifact in the group into the band
        for i in idxs:
            x0, y0 = art_anchor_out[ARTIFACTS[i]["file"]]
            ax.add_patch(FancyArrowPatch(
                (x0, y0), (USE_X - 0.04, y0),
                arrowstyle="-|>", mutation_scale=11,
                linewidth=1.15, color=edge, alpha=0.6, zorder=1))

    # query-time band gets the pipeline order spelled out, tying to the other diagram
    q_top = _row_y(min(groups["query"]))
    q_bot = _row_y(max(groups["query"])) - ROW_H
    # Centred in the band. Anchoring these to q_bot left the tall query-time band with a
    # large hole in the middle and the text crowded at the floor.
    q_mid = (q_top + q_bot) / 2
    ax.text(USE_X + 0.20, q_mid + 0.42,
            "retriever  ->  resolver  ->  validator\n"
            "   ->  compiler  ->  executor  ->  provenance",
            fontsize=9.2, color="#1b5e20", va="center", linespacing=1.6,
            zorder=3, family="DejaVu Sans Mono")
    ax.text(USE_X + 0.20, q_mid - 0.42,
            "The resolver is the only LLM.\nThe compiler owns all arithmetic.",
            fontsize=8.9, color=MUTED, va="center", linespacing=1.55, zorder=3)
    ax.text(USE_X + USE_W - 0.16, q_top - 0.29, "see nl_dataflow",
            fontsize=8.2, color=MUTED, ha="right", va="center",
            style="italic", zorder=3)

    # ---- annotations -----------------------------------------------------------
    ax.add_patch(Rectangle((SRC_X - 0.16, ANN_Y), FIG_W - 0.94, ANN_H,
                           facecolor="#fffdf5", edgecolor="#d6c98a",
                           linewidth=1.0, zorder=1))
    ax.text(SRC_X - 0.02, ANN_Y + ANN_H - 0.22,
            "WHAT THIS MAP IS FOR", fontsize=9.6, fontweight="bold",
            color="#7d6608", va="center", zorder=3)
    for i, text in enumerate(ANNOTATIONS):
        ax.text(SRC_X - 0.02, annotation_line_y(i), f"-  {text}",
                fontsize=9.1, color="#4a4a4a", va="center", zorder=3)

    return fig


# --------------------------------------------------------------------------------------
# output -- identical contract to render_dataflow.py
# --------------------------------------------------------------------------------------


def render_svg() -> str:
    fig = _build_figure()
    buf = io.StringIO()
    fig.savefig(buf, format="svg", metadata={"Date": None})
    plt.close(fig)
    return buf.getvalue()


def render_png() -> bytes:
    fig = _build_figure()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, metadata={"Software": None})
    plt.close(fig)
    return buf.getvalue()


def write() -> None:
    SVG_PATH.write_text(render_svg(), encoding="utf-8", newline="\n")
    PNG_PATH.write_bytes(render_png())
    print(f"wrote {SVG_PATH.relative_to(SVG_PATH.parents[2])} "
          f"({SVG_PATH.stat().st_size:,} bytes)")
    print(f"wrote {PNG_PATH.relative_to(PNG_PATH.parents[2])} "
          f"({PNG_PATH.stat().st_size:,} bytes)")


def check() -> int:
    problems = []
    if not SVG_PATH.exists():
        problems.append(f"{SVG_PATH.name} is missing")
    else:
        fresh, committed = render_svg(), SVG_PATH.read_text(encoding="utf-8")
        if fresh != committed:
            problems.append(
                f"{SVG_PATH.name} is stale: {len(committed):,} bytes committed vs "
                f"{len(fresh):,} rendered"
            )
    if not PNG_PATH.exists():
        problems.append(f"{PNG_PATH.name} is missing")
    elif PNG_PATH.stat().st_size < 5000:
        problems.append(f"{PNG_PATH.name} looks truncated")

    if problems:
        for p in problems:
            print(f"STALE: {p}")
        print("\nRegenerate with: python docs/diagrams/render_sources.py --write")
        return 1
    print("diagram is current")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--write" in argv:
        write()
        return 0
    if "--check" in argv:
        return check()
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
