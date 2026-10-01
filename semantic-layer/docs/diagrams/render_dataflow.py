"""Render the metadata -> natural-language dataflow swimlane.

The question this picture exists to answer: *when someone types "why did on-time
delivery drop for India warehouses last month", which metadata artifact does each
stage of the pipeline actually read?*

The phase table in the guide says what each artifact **is**. It does not say which
stage **consumes** it, and that is the part a reader needs in order to believe the
architecture -- particularly the two boundaries most such diagrams blur:

* Phases P1 and P2 (technical metadata, standardized metadata) are consumed at
  **build** time, by `sql/` and the warehouse generator. They are not read while
  answering a question. Drawing them as inputs to a query-time stage is the single
  most common inaccuracy in diagrams of this kind, so they get their own band.
* The **resolver** decides *which* governed metric a question means. The **compiler**
  owns every piece of arithmetic. Nothing reads the glossary after the gates, which is
  why synonym choice cannot influence a number.

The graph is declared as data (`STAGES`, `ARTIFACTS`, `EDGES`) and drawn from that
declaration, so `tests/test_diagram.py` can check the arrows against the real module
sources. An edge claiming `compiler.py` reads `03_glossary.yml` fails the suite rather
than quietly misinforming a reader.

Determinism: matplotlib embeds a creation timestamp and salts element ids, either of
which would make the committed SVG differ on every run and `--check` permanently red.
Both are pinned below. No wall-clock and no randomness anywhere, consistent with the
rest of the project.

    python docs/diagrams/render_dataflow.py --write    # regenerate SVG + PNG
    python docs/diagrams/render_dataflow.py --check    # fail if committed output is stale
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["svg.hashsalt"] = "semantic-layer-nl"
matplotlib.rcParams["svg.fonttype"] = "path"  # no font dependency in the committed SVG

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle  # noqa: E402

HERE = Path(__file__).resolve().parent
SVG_PATH = HERE / "nl_dataflow.svg"
PNG_PATH = HERE / "nl_dataflow.png"

# --------------------------------------------------------------------------------------
# the graph, as data
# --------------------------------------------------------------------------------------

STAGES = [
    {"key": "retriever", "num": 1, "label": "RETRIEVER",
     "sub": "assemble the\ngoverned choices", "llm": False},
    {"key": "resolver", "num": 2, "label": "RESOLVER",
     "sub": "pick which metric\n(the only LLM)", "llm": True},
    {"key": "validator", "num": 3, "label": "VALIDATOR",
     "sub": "7 gates\nfail closed", "llm": False},
    {"key": "compiler", "num": 4, "label": "COMPILER",
     "sub": "owns ALL\narithmetic", "llm": False},
    {"key": "executor", "num": 5, "label": "EXECUTOR",
     "sub": "read-only\nDuckDB", "llm": False},
    {"key": "provenance", "num": 6, "label": "PROVENANCE",
     "sub": "the number and\nits defence", "llm": False},
]

# Used by the drift test: the arrow must correspond to this module reading that file.
STAGE_MODULE = {
    "retriever": "src/semantic/retriever.py",
    "resolver": "src/semantic/resolver.py",
    "validator": "src/semantic/validator.py",
    "compiler": "src/semantic/compiler.py",
    "executor": "src/semantic/executor.py",
    "provenance": "src/semantic/provenance.py",
}

# phase: "contract" -- the acceptance oracle, framing rather than an input
#        "build"    -- consumed before query time, by sql/ and the generator
#        "query"    -- read while answering a question
ARTIFACTS = [
    {"file": "00_kpi_contract.md", "p": "P0", "phase": "contract",
     "role": "what the number must mean"},
    {"file": "01_technical_metadata.json", "p": "P1", "phase": "build",
     "role": "physical columns and types"},
    {"file": "02_standardized_metadata.json", "p": "P2", "phase": "build",
     "role": "canonical names, declared grain"},
    {"file": "03_glossary.yml", "p": "P3", "phase": "query",
     "role": "business vocabulary"},
    {"file": "03_column_bindings.yml", "p": "P3", "phase": "query",
     "role": "term -> physical column"},
    {"file": "04_process_model.yml", "p": "P4", "phase": "query",
     "role": "plan-to-deliver phases"},
    {"file": "05_semantic_model.yml", "p": "P5", "phase": "query",
     "role": "the governed metric definitions"},
    {"file": "06_dq_rules.yml", "p": "P6", "phase": "query",
     "role": "quality contract"},
    {"file": "07_catalog_asset.json", "p": "P7", "phase": "query",
     "role": "ownership, lineage, governance"},
]

# `label` is *what* is consumed. "05_semantic_model.yml -> compiler" is not
# information; "numerator, denominator, exclusion predicates" is the whole point.
#
# `reader` is the module that actually opens the file, which is not always the stage that
# consumes it. The validator and compiler never touch the filesystem: they receive a
# `SemanticModel` that `loader.py` parsed, and provenance gets its badge from `dq.py`.
# That indirection is a design property worth being precise about -- a stage that cannot
# open a file cannot quietly read a different one -- so the edge records the reader rather
# than pretending the stage does its own IO. The drift test greps `reader`, then separately
# confirms the stage consumes the loaded object.
EDGES = [
    {"file": "03_glossary.yml", "stage": "retriever", "phase": "query",
     "reader": "src/semantic/retriever.py",
     "label": "synonyms: \"OTD\" -> on_time_delivery_pct, \"India\" -> IN"},
    {"file": "03_column_bindings.yml", "stage": "retriever", "phase": "query",
     "reader": "src/semantic/retriever.py",
     "label": "\"warehouse\" -> fact_order_delivery.warehouse"},
    {"file": "04_process_model.yml", "stage": "retriever", "phase": "query",
     "reader": "src/semantic/retriever.py",
     "label": "12 phase keys, so \"why\" has nameable causes"},
    {"file": "05_semantic_model.yml", "stage": "retriever", "phase": "query",
     "reader": "src/semantic/loader.py",
     "label": "approved metrics only, grain, time dimension"},
    # The plan's edge table put gate 3's `allowed_values` on 03_glossary.yml. The drift
    # test caught it: validator.py reads `dim.get("allowed_values")` off the dimension in
    # the semantic model and names no metadata file at all. Corrected here, and the
    # correction is worth more than the original claim -- the validator reads NOTHING but
    # the semantic model, so vocabulary cannot influence a gate.
    {"file": "05_semantic_model.yml", "stage": "validator", "phase": "query",
     "reader": "src/semantic/loader.py",
     "label": "approval_state, declared dims, join cardinality -> gates 1,2,4,5"},
    {"file": "05_semantic_model.yml", "stage": "validator", "phase": "query",
     "reader": "src/semantic/loader.py",
     "label": "allowed_values -> gate 3 rejects region = 'MARS'"},
    {"file": "05_semantic_model.yml", "stage": "compiler", "phase": "query",
     "reader": "src/semantic/loader.py",
     "label": "numerator, denominator, exclusion predicates, the join"},
    {"file": "06_dq_rules.yml", "stage": "provenance", "phase": "query",
     "reader": "src/semantic/dq.py",
     "label": "rule results -> TRUSTED / DEGRADED / BLOCKED"},
    {"file": "07_catalog_asset.json", "stage": "provenance", "phase": "query",
     "reader": "src/semantic/provenance.py",
     "label": "owner, 11-step lineage, governance fields"},
]

ANNOTATIONS = [
    "The resolver picks WHICH governed metric the question means. "
    "The compiler owns ALL arithmetic.",
    "A question never becomes SQL until all 7 gates pass. "
    "A gate that cannot be evaluated fails closed.",
    "P1 and P2 are consumed at BUILD time, not while answering. Nothing after the "
    "retriever reads the glossary -- vocabulary cannot influence a gate or a number.",
]

# --------------------------------------------------------------------------------------
# layout
# --------------------------------------------------------------------------------------

# Three columns: artifacts on the left, clear air in the middle for the arrows to
# travel through, stage lanes on the right. An earlier version put the "what each stage
# reads" list in a middle column and it collided with both the warehouse box and the
# arrows crossing it -- the labels now live INSIDE the lane that reads them, which is
# also where a reader looks for them.
FIG_W, FIG_H = 21.0, 14.4

# Artifact column
ART_X, ART_W, ART_H = 0.55, 4.60, 0.62
ART_GAP = 0.28
ART_BAND_GAP = 0.34      # extra air where build time becomes query time
# The contract box carries a two-line caption underneath and the build band carries a
# label above, so the gap between them has to hold both. Sized deliberately, not by feel:
# at 0.34 the two captions overprinted each other.
ART_CONTRACT_GAP = 1.05
ART_TOP = 12.85          # y of the first (topmost) box's top edge

# Stage band. Heights vary: a lane is as tall as the list of artifacts it reads.
STAGE_X, STAGE_W = 10.30, 7.90
STAGE_TOP = 12.85
STAGE_GAP = 0.30
STAGE_BASE_H = 0.86      # header: number, label, one-line summary
STAGE_ROW_H = 0.38       # per artifact read: filename line + what-it-supplies line
STAGE_LIST_PAD = 0.16

COL_QUERY = "#1f4e79"
COL_BUILD = "#7f7f7f"
COL_LLM = "#8b3a62"
COL_CONTRACT = "#7d6608"
COL_EDGE = "#4a6f96"
COL_BG_BUILD = "#f2f2f2"
COL_BG_QUERY = "#eaf1f8"


def artifact_boxes() -> dict[str, dict]:
    """file -> {x, y, w, h}. Separate from drawing so the overlap test can check it.

    Ordering follows ARTIFACTS, which is phase order: the contract on top, the two
    build-time artifacts next in their own band, then the five query-time ones. A reader
    scanning top to bottom is reading the phases in the order they were produced.
    """
    boxes: dict[str, dict] = {}
    y = ART_TOP - ART_H
    for i, art in enumerate(ARTIFACTS):
        # Extra breathing room where the band changes, so the two bands read as
        # separate groups rather than one list with inconsistent spacing.
        if i > 0:
            prev = ARTIFACTS[i - 1]["phase"]
            if prev == "contract":
                gap = ART_CONTRACT_GAP
            elif prev != art["phase"]:
                gap = ART_GAP + ART_BAND_GAP
            else:
                gap = ART_GAP
            y -= ART_H + gap
        boxes[art["file"]] = {"x": ART_X, "y": y, "w": ART_W, "h": ART_H}
    return boxes


def edges_for(stage_key: str) -> list[dict]:
    """The artifacts one stage reads, in declaration order."""
    return [e for e in EDGES if e["stage"] == stage_key]


def stage_boxes() -> dict[str, dict]:
    """stage key -> {x, y, w, h}, top to bottom in pipeline order.

    Height is derived from the number of artifacts the stage reads, because the read list
    is drawn inside the lane. A fixed height would either clip the retriever's four
    entries or leave the executor's zero entries as a large empty box.
    """
    boxes: dict[str, dict] = {}
    y = STAGE_TOP
    for stage in STAGES:
        rows = len(edges_for(stage["key"]))
        h = STAGE_BASE_H + (rows * STAGE_ROW_H + STAGE_LIST_PAD if rows else 0.0)
        y -= h
        boxes[stage["key"]] = {"x": STAGE_X, "y": y, "w": STAGE_W, "h": h}
        y -= STAGE_GAP
    return boxes


# --------------------------------------------------------------------------------------
# drawing
# --------------------------------------------------------------------------------------


def _box(ax, x, y, w, h, *, edge, face, lw=1.4, radius=0.06, z=2, ls="solid"):
    patch = FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad=0,rounding_size={radius}",
        linewidth=lw, edgecolor=edge, facecolor=face, zorder=z, linestyle=ls,
    )
    ax.add_patch(patch)
    return patch


def _build_figure():
    fig = plt.figure(figsize=(FIG_W, FIG_H))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, FIG_W)
    ax.set_ylim(0, FIG_H)
    ax.axis("off")

    arts = artifact_boxes()
    stages = stage_boxes()

    # ---- title -----------------------------------------------------------------------
    ax.text(FIG_W / 2, FIG_H - 0.42,
            "How governed metadata answers a natural-language question",
            ha="center", va="center", fontsize=19, fontweight="bold", color="#1a1a1a")
    ax.text(FIG_W / 2, FIG_H - 0.85,
            '"Why did on-time delivery drop for India warehouses last month?"'
            "   ->   87.3%, down 8.9pp, largest contributor: quality inspection",
            ha="center", va="center", fontsize=11.5, style="italic", color="#555555")

    # ---- band backgrounds ------------------------------------------------------------
    build_files = [a["file"] for a in ARTIFACTS if a["phase"] == "build"]
    query_files = [a["file"] for a in ARTIFACTS if a["phase"] == "query"]

    for files, colour, label in (
        (build_files, COL_BG_BUILD, "BUILD TIME  (before any question is asked)"),
        (query_files, COL_BG_QUERY, "QUERY TIME  (read while answering)"),
    ):
        top = max(arts[f]["y"] + arts[f]["h"] for f in files)
        bot = min(arts[f]["y"] for f in files)
        pad = 0.18
        # The band label sits ABOVE its group. Below, it collided with the next
        # artifact box down -- the band gap is not large enough to hold a caption.
        ax.add_patch(Rectangle(
            (ART_X - pad, bot - pad), ART_W + 2 * pad, (top - bot) + 2 * pad,
            facecolor=colour, edgecolor="#cccccc", linewidth=0.8, zorder=1,
        ))
        ax.text(ART_X - pad + 0.04, top + pad + 0.14, label,
                fontsize=8.4, color="#666666", fontweight="bold", va="center", zorder=3)

    # ---- artifact boxes --------------------------------------------------------------
    for art in ARTIFACTS:
        b = arts[art["file"]]
        colour = {"build": COL_BUILD, "contract": COL_CONTRACT}.get(
            art["phase"], COL_QUERY)
        _box(ax, b["x"], b["y"], b["w"], b["h"],
             edge=colour, face="white", z=2,
             ls="dashed" if art["phase"] == "contract" else "solid")
        ax.text(b["x"] + 0.14, b["y"] + b["h"] * 0.66, art["p"],
                fontsize=9, fontweight="bold", color=colour, va="center", zorder=3)
        ax.text(b["x"] + 0.62, b["y"] + b["h"] * 0.66, art["file"],
                fontsize=10, family="monospace", color="#1a1a1a", va="center", zorder=3)
        ax.text(b["x"] + 0.62, b["y"] + b["h"] * 0.25, art["role"],
                fontsize=8.6, color="#666666", va="center", zorder=3)

    # ---- the contract is a framing band, not an input --------------------------------
    # Placed BELOW its box rather than to the right: the space to the right is the arrow
    # corridor, and an earlier version put this text straight through the retriever lane's
    # incoming edges.
    c = arts["00_kpi_contract.md"]
    ax.text(c["x"] + 0.10, c["y"] - 0.20,
            "the acceptance oracle -- every stage below is checked against it;\n"
            "no stage reads it at runtime",
            fontsize=8.4, color=COL_CONTRACT, va="top", zorder=3)

    # ---- warehouse box, fed by the build-time artifacts ------------------------------
    b1, b2 = arts["01_technical_metadata.json"], arts["02_standardized_metadata.json"]
    wh_x, wh_w = ART_X + ART_W + 0.72, 3.55
    wh_y = b2["y"]
    wh_h = (b1["y"] + b1["h"]) - wh_y
    _box(ax, wh_x, wh_y, wh_w, wh_h, edge=COL_BUILD, face="#fafafa", lw=1.4)
    ax.text(wh_x + wh_w / 2, wh_y + wh_h * 0.68, "sql/  ->  warehouse.duckdb",
            ha="center", va="center", fontsize=10.5, family="monospace",
            fontweight="bold", color="#404040", zorder=3)
    ax.text(wh_x + wh_w / 2, wh_y + wh_h * 0.34,
            "fact_order_delivery\nfact_production_order\ndim_process_phase",
            ha="center", va="center", fontsize=8.2, color="#666666",
            family="monospace", linespacing=1.5, zorder=3)
    for b in (b1, b2):
        ax.add_patch(FancyArrowPatch(
            (b["x"] + b["w"], b["y"] + b["h"] / 2),
            (wh_x, b["y"] + b["h"] / 2),
            arrowstyle="-|>", mutation_scale=12, linewidth=1.2,
            color=COL_BUILD, shrinkA=2, shrinkB=2, zorder=2,
        ))
    ax.text(wh_x + wh_w / 2, wh_y + wh_h + 0.16,
            "consumed once, at build time", ha="center", fontsize=8.0,
            color=COL_BUILD, style="italic", zorder=3)
    # The note about what the executor reads belongs in the executor's own lane, which has
    # room: placed under the warehouse box it sat in the arrow corridor with three edges
    # crossing it.
    ex = stages["executor"]
    ax.text(ex["x"] + 3.05, ex["y"] + ex["h"] / 2 - 0.26,
            "reads the warehouse, not the metadata -- it cannot rewrite the SQL",
            fontsize=8.0, color="#777777", style="italic", va="center", zorder=3)

    # ---- stage lanes, each listing what it reads --------------------------------------
    for stage in STAGES:
        b = stages[stage["key"]]
        colour = COL_LLM if stage["llm"] else COL_QUERY
        face = "#fdf3f8" if stage["llm"] else "#f4f8fc"
        _box(ax, b["x"], b["y"], b["w"], b["h"], edge=colour, face=face, lw=1.7)
        head_y = b["y"] + b["h"] - 0.30
        ax.text(b["x"] + 0.30, head_y, f"{stage['num']}",
                fontsize=15, fontweight="bold", color=colour, va="center", zorder=3)
        ax.text(b["x"] + 0.80, head_y, stage["label"],
                fontsize=12, fontweight="bold", color=colour, va="center", zorder=3)
        ax.text(b["x"] + 2.90, head_y, stage["sub"].replace("\n", "  |  "),
                fontsize=8.8, color="#555555", va="center", zorder=3)
        ax.text(b["x"] + b["w"] - 0.18, head_y,
                STAGE_MODULE[stage["key"]].split("/")[-1],
                fontsize=8.2, family="monospace", color="#999999",
                ha="right", va="center", zorder=3)
        if stage["llm"]:
            ax.text(b["x"] + b["w"] - 0.18, head_y - 0.30,
                    "LLM  |  needs a key", fontsize=8.4, fontweight="bold",
                    color=COL_LLM, ha="right", va="center", zorder=3)

        # The read list, inside the lane. This is the diagram's actual content: not
        # "the retriever exists" but "the retriever reads synonyms out of the glossary".
        ly = b["y"] + b["h"] - STAGE_BASE_H - 0.06
        for e in edges_for(stage["key"]):
            ax.text(b["x"] + 0.42, ly, e["file"], fontsize=8.2, family="monospace",
                    color="#1a1a1a", va="center", zorder=3)
            ax.text(b["x"] + 3.05, ly, e["label"], fontsize=8.0, color="#5a5a5a",
                    va="center", zorder=3)
            # Which module opens the file. Shown because it is often NOT this stage:
            # the validator and compiler never touch the filesystem, and hiding that
            # would make the picture less accurate than the data behind it.
            reader = e.get("reader", "").split("/")[-1]
            if reader and reader != STAGE_MODULE[stage["key"]].split("/")[-1]:
                ax.text(b["x"] + b["w"] - 0.18, ly, f"via {reader}",
                        fontsize=7.4, family="monospace", color="#aaaaaa",
                        ha="right", va="center", zorder=3)
            ly -= STAGE_ROW_H

    # ---- the pipeline spine: stage N -> stage N+1 -------------------------------------
    for a, b in zip(STAGES, STAGES[1:]):
        ba, bb = stages[a["key"]], stages[b["key"]]
        x = ba["x"] + 0.30
        ax.add_patch(FancyArrowPatch(
            (x, ba["y"]), (x, bb["y"] + bb["h"]),
            arrowstyle="-|>", mutation_scale=13, linewidth=1.6,
            color=COL_QUERY, shrinkA=1, shrinkB=1, zorder=2,
        ))

    # ---- the handoff labels on the spine ---------------------------------------------
    handoffs = {
        "resolver": "governed context (cached prefix)",
        "validator": "QueryIntent  (JSON, schema-checked)",
        "compiler": "validated intent  --  7/7 gates",
        "executor": "SQL + bound params",
        "provenance": "result rows",
    }
    for key, text in handoffs.items():
        b = stages[key]
        ax.text(b["x"] + 0.52, b["y"] + b["h"] + 0.145, text,
                fontsize=8.2, color="#3a6288", style="italic", va="center", zorder=3)

    # ---- artifact -> stage edges -----------------------------------------------------
    # Curvature is assigned per target stage so parallel arrows into the same lane stay
    # visually distinct instead of collapsing onto one path. They land on the lane's left
    # edge at the row for the artifact they carry, so an arrow points at its own label.
    rads = {"retriever": 0.12, "validator": -0.10, "compiler": 0.08,
            "provenance": -0.12}
    for e in EDGES:
        a, b = arts[e["file"]], stages[e["stage"]]
        rows = edges_for(e["stage"])
        row = rows.index(e)
        ty = b["y"] + b["h"] - STAGE_BASE_H - 0.06 - row * STAGE_ROW_H
        ax.add_patch(FancyArrowPatch(
            (a["x"] + a["w"], a["y"] + a["h"] / 2),
            (b["x"], ty),
            arrowstyle="-|>", mutation_scale=11, linewidth=1.05,
            color=COL_EDGE, alpha=0.7,
            connectionstyle=f"arc3,rad={rads.get(e['stage'], 0.0)}",
            shrinkA=3, shrinkB=3, zorder=2,
        ))

    # ---- the refusal path ------------------------------------------------------------
    # Drawn to the LEFT of the validator lane, into the arrow corridor. An earlier version
    # put it to the right, where it was clipped off the figure edge.
    v = stages["validator"]
    ax.add_patch(FancyArrowPatch(
        (v["x"], v["y"] + 0.16), (v["x"] - 1.05, v["y"] - 0.34),
        arrowstyle="-|>", mutation_scale=11, linewidth=1.3,
        color="#b03030", connectionstyle="arc3,rad=0.25",
        shrinkA=2, shrinkB=2, zorder=3,
    ))
    ax.text(v["x"] - 1.10, v["y"] - 0.42,
            "any gate fails  ->  REFUSED\nthe gate is named, no number\nis printed at all",
            fontsize=8.6, color="#b03030", fontweight="bold", va="top",
            ha="right", zorder=3)

    # ---- the answer ------------------------------------------------------------------
    p = stages["provenance"]
    ans_h = 1.10
    ans_y = p["y"] - 0.62 - ans_h
    _box(ax, STAGE_X, ans_y, STAGE_W, ans_h, edge="#1e7145", face="#f1f8f3", lw=1.7)
    ax.add_patch(FancyArrowPatch(
        (STAGE_X + 0.30, p["y"]), (STAGE_X + 0.30, ans_y + ans_h),
        arrowstyle="-|>", mutation_scale=13, linewidth=1.6,
        color="#1e7145", shrinkA=1, shrinkB=1, zorder=2,
    ))
    ax.text(STAGE_X + 0.80, ans_y + ans_h - 0.30, "ANSWER  +  ITS DEFENCE",
            fontsize=11.5, fontweight="bold", color="#1e7145", va="center", zorder=3)
    ax.text(STAGE_X + 0.80, ans_y + 0.34,
            "value  |  arithmetic 48 / 55  |  grain  |  window  |  exclusions applied\n"
            "lineage  |  trust badge  |  7/7 gates  |  the SQL that produced it",
            fontsize=8.6, color="#2f5d43", va="center", linespacing=1.6, zorder=3)

    # ---- annotations: the architectural rules ----------------------------------------
    ann_h, ann_w = 1.42, 9.35
    ann_y = 0.42
    ax.add_patch(Rectangle((ART_X - 0.20, ann_y), ann_w, ann_h,
                           facecolor="#fffdf5", edgecolor="#d6c98a",
                           linewidth=1.0, zorder=1))
    ax.text(ART_X - 0.02, ann_y + ann_h - 0.26, "THE RULES THIS LAYOUT ENFORCES",
            fontsize=9.4, fontweight="bold", color="#7d6608", va="center", zorder=3)
    for i, text in enumerate(ANNOTATIONS):
        ax.text(ART_X - 0.02, ann_y + ann_h - 0.62 - i * 0.33, f"-  {text}",
                fontsize=9.0, color="#4a4a4a", va="center", zorder=3)

    return fig


# --------------------------------------------------------------------------------------
# output
# --------------------------------------------------------------------------------------


def render_svg() -> str:
    """SVG source. `metadata={"Date": None}` drops the embedded creation timestamp.

    Without it the file differs on every run and `--check` is permanently red, which is
    the fastest way to teach a team to ignore a drift check.
    """
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
    """Exit 1 if the committed output is stale.

    Only the SVG is compared byte-for-byte. PNG encoding varies across matplotlib and
    libpng builds in ways that say nothing about the diagram's content, so comparing it
    strictly would fail on a different machine for no real reason; its existence and
    plausible size are checked instead.
    """
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
        print("\nRegenerate with: python docs/diagrams/render_dataflow.py --write")
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
