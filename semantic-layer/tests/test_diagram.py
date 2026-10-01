"""The diagram is documentation, so it can drift from the code. These tests
make the drift fail loudly rather than mislead a reader.

The load-bearing test is test_every_declared_edge_is_real: it reads the edge list
out of the renderer and greps the actual module source for the artifact filename,
so an edge the code does not have cannot survive in the picture.
"""
import subprocess, sys
import pytest
from src.semantic.constants import REPO_ROOT

DIAGRAM_DIR = REPO_ROOT / "docs" / "diagrams"

def test_committed_output_exists_and_is_nonempty():
    for name in ("nl_dataflow.svg", "nl_dataflow.png"):
        p = DIAGRAM_DIR / name
        assert p.exists(), f"missing {name}"
        assert p.stat().st_size > 5000, f"{name} looks truncated"

def test_renderer_check_mode_says_committed_output_is_current():
    """--check must fail if someone edits the renderer and forgets to regenerate."""
    p = subprocess.run(
        [sys.executable, str(DIAGRAM_DIR / "render_dataflow.py"), "--check"],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert p.returncode == 0, f"committed diagram is stale, run --write:\n{p.stdout}{p.stderr}"

def test_all_six_pipeline_stages_are_lanes():
    from docs.diagrams.render_dataflow import STAGES
    keys = [s["key"] for s in STAGES]
    assert keys == ["retriever", "resolver", "validator",
                    "compiler", "executor", "provenance"]

def test_all_nine_artifacts_appear():
    """All 8 phases P0-P7, which is 9 files (phase 3 emits two)."""
    from docs.diagrams.render_dataflow import ARTIFACTS
    assert {a["file"] for a in ARTIFACTS} == {
        "00_kpi_contract.md", "01_technical_metadata.json",
        "02_standardized_metadata.json", "03_glossary.yml",
        "03_column_bindings.yml", "04_process_model.yml",
        "05_semantic_model.yml", "06_dq_rules.yml", "07_catalog_asset.json",
    }

def test_every_artifact_file_actually_exists():
    from docs.diagrams.render_dataflow import ARTIFACTS
    from src.semantic.constants import METADATA_DIR
    for a in ARTIFACTS:
        assert (METADATA_DIR / a["file"]).exists(), f"{a['file']} does not exist"

def test_every_declared_edge_is_real():
    """An arrow from artifact X to stage Y must correspond to real code reading X.

    This is what stops the diagram becoming a pretty lie, and it has already earned
    its keep twice: it caught the plan's claim that the validator reads
    `allowed_values` from `03_glossary.yml` (it reads it from the semantic model),
    and it forced the `reader` field into the edge declarations, because the
    validator and compiler never open a file at all -- they receive a SemanticModel
    that `loader.py` parsed.

    So the assertion is in two halves: the declared reader must name the file, and
    the consuming stage must name the thing the reader produced. A stage that
    cannot open a file cannot quietly read a different one, which is a stronger
    property than "the module mentions the filename".

    Build-time artifacts are exempt: they feed sql/ and the generator, not a
    query-time module.
    """
    from docs.diagrams.render_dataflow import EDGES, STAGE_MODULE
    for e in EDGES:
        if e.get("phase") == "build":
            continue
        reader = e.get("reader")
        assert reader, f"edge declares no reader: {e}"
        reader_src = (REPO_ROOT / reader).read_text(encoding="utf-8")
        stem = e["file"].split(".")[0]
        assert stem in reader_src or e["file"] in reader_src, (
            f"diagram claims {reader} opens {e['file']}, but its source never "
            f"names it. Either the edge is wrong or the module changed."
        )
        # The consuming stage must actually use what the reader produced.
        module = STAGE_MODULE[e["stage"]]
        stage_src = (REPO_ROOT / module).read_text(encoding="utf-8")
        if reader == module:
            continue  # the stage is its own reader; already asserted above
        handoff = {
            "src/semantic/loader.py": ("SemanticModel", "model"),
            "src/semantic/dq.py": ("DQReport", "dq"),
            "src/semantic/provenance.py": ("Answer",),
            "src/semantic/retriever.py": ("build_context",),
        }[reader]
        assert any(h in stage_src for h in handoff), (
            f"{module} consumes {e['file']} via {reader}, but never references "
            f"any of {handoff}"
        )

def test_no_edge_claims_the_compiler_reads_the_glossary():
    """Architectural invariant: vocabulary resolution happens BEFORE the gates.

    If the compiler read the glossary, synonym choice would influence arithmetic,
    which is exactly the coupling this architecture exists to prevent.
    """
    from docs.diagrams.render_dataflow import EDGES
    bad = [e for e in EDGES
           if e["stage"] == "compiler" and e["file"].startswith("03_")]
    assert bad == [], f"compiler must not depend on vocabulary: {bad}"

def test_resolver_is_the_only_llm_lane():
    from docs.diagrams.render_dataflow import STAGES
    llm = [s["key"] for s in STAGES if s.get("llm")]
    assert llm == ["resolver"]

def test_diagram_is_deterministic(tmp_path):
    """Same input, same bytes -- so the committed SVG diffs cleanly."""
    from docs.diagrams.render_dataflow import render_svg
    a = render_svg()
    b = render_svg()
    assert a == b


# --- Added beyond the plan ---------------------------------------------------
# The plan's 9 tests check the graph is accurate. They do not check it is
# LEGIBLE, and an accurate illegible diagram has still failed at its only job.
# These check the things I actually had to fix by looking at the PNG.

def test_no_artifact_is_drawn_without_being_consumed_or_labelled_why_not():
    """Every artifact either feeds a query-time stage or is explicitly marked
    build-time/contract. An artifact floating with no arrow and no explanation
    reads as an oversight in the pipeline rather than a deliberate boundary."""
    from docs.diagrams.render_dataflow import ARTIFACTS, EDGES
    consumed = {e["file"] for e in EDGES if e.get("phase") != "build"}
    for a in ARTIFACTS:
        if a["file"] in consumed:
            continue
        assert a.get("phase") in ("build", "contract"), (
            f"{a['file']} has no query-time edge and no phase marking; a reader "
            f"cannot tell whether that is deliberate"
        )


def test_every_edge_carries_a_label_saying_what_is_consumed():
    """'05_semantic_model.yml -> compiler' is not information; 'numerator,
    denominator, exclusion predicates' is. The labels are the diagram's content."""
    from docs.diagrams.render_dataflow import EDGES
    for e in EDGES:
        assert e.get("label"), f"unlabelled edge: {e}"
        assert len(e["label"]) > 8, f"label too thin to be useful: {e}"


def test_the_arithmetic_boundary_is_stated_on_the_figure():
    """The one sentence a reader must leave with. If it is not drawn, the picture
    shows six boxes and no argument."""
    from docs.diagrams.render_dataflow import ANNOTATIONS
    text = " ".join(ANNOTATIONS).lower()
    assert "arithmetic" in text
    assert "compiler" in text and "resolver" in text


def test_no_two_artifact_boxes_overlap():
    """Found by looking at the PNG: computed rows silently collided once the
    build-time band was added. Overlapping labels are unreadable, and no other
    test can see it."""
    from docs.diagrams.render_dataflow import artifact_boxes
    boxes = artifact_boxes()
    for i, (ka, a) in enumerate(boxes.items()):
        for kb, b in list(boxes.items())[i + 1:]:
            separated = (
                a["y"] + a["h"] <= b["y"] + 1e-9 or b["y"] + b["h"] <= a["y"] + 1e-9
                or a["x"] + a["w"] <= b["x"] + 1e-9 or b["x"] + b["w"] <= a["x"] + 1e-9
            )
            assert separated, f"{ka} overlaps {kb}"


def test_every_edge_targets_a_declared_stage_and_artifact():
    """A typo'd stage key would silently draw an arrow to nowhere."""
    from docs.diagrams.render_dataflow import ARTIFACTS, EDGES, STAGES, STAGE_MODULE
    stage_keys = {s["key"] for s in STAGES}
    files = {a["file"] for a in ARTIFACTS}
    for e in EDGES:
        assert e["file"] in files, f"edge from unknown artifact: {e}"
        assert e["stage"] in stage_keys, f"edge to unknown stage: {e}"
    assert set(STAGE_MODULE) == stage_keys, "STAGE_MODULE and STAGES disagree"
    for module in STAGE_MODULE.values():
        assert (REPO_ROOT / module).exists(), f"{module} does not exist"


def test_the_svg_contains_no_timestamp_so_it_diffs_cleanly():
    """matplotlib embeds a creation date by default, which would make every
    regeneration a spurious diff and --check permanently red."""
    from docs.diagrams.render_dataflow import render_svg
    svg = render_svg()
    assert "dc:date" not in svg and "<dc:date>" not in svg
    # Belt and braces: no 4-digit-year date string anywhere in the metadata block.
    import re
    head = svg[:4000]
    assert not re.search(r"20\d\d-\d\d-\d\dT\d\d:", head), head[:600]


# ==============================================================================
# metadata_sources -- the provenance map (render_sources.py)
# ==============================================================================
# nl_dataflow answers "which stage reads which artifact when a question arrives".
# This one answers "where did each artifact come from", which is the claim most
# likely to be flattering fiction: it is much easier to draw an arrow from "SAP
# DDIC" to an artifact than to have actually got that content from SAP.
#
# So the load-bearing test here is test_every_source_claim_is_the_artifacts_own_claim.
# Every edge declares a `probe` string that must occur in the artifact it points at.
# An arrow whose evidence is not in the file fails, rather than shipping as a
# plausible-looking provenance claim nobody can check.

def test_sources_committed_output_exists_and_is_nonempty():
    for name in ("metadata_sources.svg", "metadata_sources.png"):
        p = DIAGRAM_DIR / name
        assert p.exists(), f"missing {name}"
        assert p.stat().st_size > 5000, f"{name} looks truncated"


def test_sources_renderer_check_mode_says_committed_output_is_current():
    p = subprocess.run(
        [sys.executable, str(DIAGRAM_DIR / "render_sources.py"), "--check"],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert p.returncode == 0, f"committed diagram is stale, run --write:\n{p.stdout}{p.stderr}"


def test_every_source_claim_is_the_artifacts_own_claim():
    """The test this diagram exists to survive.

    Each edge says "artifact X came from source Y" and backs it with a `probe`
    string. If that string is not in X, the diagram is asserting a provenance the
    file itself does not support -- e.g. claiming P4 came from Manufacturing
    Excellence when no such owner is named anywhere in 04_process_model.yml.

    Provenance that cannot be checked against the artifact is decoration.
    """
    from docs.diagrams.render_sources import EDGES
    from src.semantic.constants import METADATA_DIR
    for e in EDGES:
        path = METADATA_DIR / e["file"]
        assert path.exists(), f"edge points at a nonexistent artifact: {e['file']}"
        text = path.read_text(encoding="utf-8")
        assert e["probe"] in text, (
            f"{e['file']} is drawn as coming from '{e['src']}', evidenced by "
            f"{e['probe']!r} -- but that string is not in the file. Either the "
            f"artifact changed or the edge was invented."
        )


def test_sources_diagram_covers_the_same_nine_artifacts_as_the_dataflow_one():
    """Two diagrams, one artifact set. If they drift a reader gets two stories."""
    from docs.diagrams.render_dataflow import ARTIFACTS as FLOW
    from docs.diagrams.render_sources import ARTIFACTS as SRC
    assert {a["file"] for a in SRC} == {a["file"] for a in FLOW}
    assert {a["p"] for a in SRC} == {a["p"] for a in FLOW}
    # Same order, so the eye tracks P0..P7 down both figures identically.
    assert [a["file"] for a in SRC] == [a["file"] for a in FLOW]


def test_when_each_artifact_is_used_agrees_with_the_dataflow_diagram():
    """`use` here and `phase` there are the same claim, drawn twice.

    This is the specific way the pair could mislead: this figure putting
    05_semantic_model.yml in the BUILD TIME band while the other one draws three
    query-time arrows out of it. Neither diagram alone can catch that.
    """
    from docs.diagrams.render_dataflow import ARTIFACTS as FLOW
    from docs.diagrams.render_sources import ARTIFACTS as SRC, USE
    phase = {a["file"]: a["phase"] for a in FLOW}
    for a in SRC:
        assert a["use"] == phase[a["file"]], (
            f"{a['file']}: sources map says '{a['use']}', dataflow says "
            f"'{phase[a['file']]}'"
        )
        assert a["use"] in USE, f"{a['file']} uses an undeclared band"


def test_exactly_one_artifact_is_machine_harvestable():
    """The diagram's entire argument, as an assertion.

    If a second artifact is ever marked harvested, the subtitle, the legend count
    and the first annotation line all become false at once. This is the number the
    reader is meant to leave with, so it gets a test rather than a caption.
    """
    from docs.diagrams.render_sources import ARTIFACTS
    harvested = [a["file"] for a in ARTIFACTS if a["kind"] == "harvested"]
    assert harvested == ["01_technical_metadata.json"], harvested


def test_provenance_kind_counts_match_the_legend_and_the_prose():
    """1 harvested / 4 derived / 4 authored. The legend renders these counts from
    ARTIFACTS, so this pins the claim the article and post both quote."""
    from docs.diagrams.render_sources import ARTIFACTS, KIND
    counts = {k: sum(1 for a in ARTIFACTS if a["kind"] == k) for k in KIND}
    assert counts == {"harvested": 1, "derived": 4, "authored": 4}, counts
    assert sum(counts.values()) == len(ARTIFACTS) == 9


def test_every_artifact_declares_an_owner_and_a_collection_method():
    """"Where did this come from" is unanswered without both. An artifact with no
    named owner is the failure mode the last annotation line promises is absent."""
    from docs.diagrams.render_sources import ARTIFACTS
    for a in ARTIFACTS:
        assert a.get("owner"), f"{a['file']} has no owner"
        assert a.get("how") and len(a["how"]) > 8, f"{a['file']} how: too thin"
        assert a.get("gives") and len(a["gives"]) > 8, f"{a['file']} adds: too thin"


def test_every_sources_edge_targets_a_declared_source_and_artifact():
    """A typo'd source key would raise at render time, but a typo'd filename would
    silently draw an arrow into nothing."""
    from docs.diagrams.render_sources import ARTIFACTS, EDGES, KIND, SOURCES
    keys = {s["key"] for s in SOURCES}
    files = {a["file"] for a in ARTIFACTS}
    for e in EDGES:
        assert e["src"] in keys, f"edge from unknown source: {e}"
        assert e["file"] in files, f"edge to unknown artifact: {e}"
    for s in SOURCES:
        assert s["kind"] in KIND, f"source {s['key']} has an unknown kind"


def test_every_artifact_has_at_least_one_incoming_source_edge():
    """An artifact drawn with no arrow reads as having appeared from nowhere, which
    is exactly the impression this diagram exists to dispel."""
    from docs.diagrams.render_sources import ARTIFACTS, EDGES
    sourced = {e["file"] for e in EDGES}
    missing = [a["file"] for a in ARTIFACTS if a["file"] not in sourced]
    assert missing == [], f"artifacts with no declared provenance: {missing}"


def test_the_organising_insight_is_stated_on_the_figure():
    """Someone who only looks at the picture must still get the point."""
    from docs.diagrams.render_sources import ANNOTATIONS
    text = " ".join(ANNOTATIONS).lower()
    assert "harvestable" in text and "one" in text
    assert "grain" in text          # what a crawler cannot give you
    assert "owner" in text          # who to ask when the number is wrong


def test_no_two_sources_diagram_boxes_overlap():
    """Found by reading the PNG, twice: the annotation strip sat on top of the
    'Business + governance' source box, and the three-line detail text fell
    through the bottom of a 0.98-high box. Asserted against the renderer's own
    layout_boxes() so the test cannot drift from what is drawn."""
    from docs.diagrams.render_sources import layout_boxes
    boxes = layout_boxes()
    items = list(boxes.items())
    for i, (ka, a) in enumerate(items):
        for kb, b in items[i + 1:]:
            separated = (
                a["y"] + a["h"] <= b["y"] + 1e-9 or b["y"] + b["h"] <= a["y"] + 1e-9
                or a["x"] + a["w"] <= b["x"] + 1e-9 or b["x"] + b["w"] <= a["x"] + 1e-9
            )
            assert separated, f"{ka} overlaps {kb}: {a} vs {b}"


def test_every_annotation_line_falls_inside_the_annotation_box():
    """The fourth line rendered at y=0.19 against a box floor of 0.24 -- off the
    strip, on top of nothing, and only visible in the PNG."""
    from docs.diagrams.render_sources import ANNOTATIONS, ANN_H, ANN_Y, annotation_line_y
    for i, text in enumerate(ANNOTATIONS):
        y = annotation_line_y(i)
        assert ANN_Y + 0.04 < y < ANN_Y + ANN_H - 0.04, (
            f"annotation line {i} ({text[:40]}...) at y={y:.2f} is outside the box "
            f"{ANN_Y:.2f}..{ANN_Y + ANN_H:.2f}"
        )


def test_everything_fits_inside_the_figure():
    from docs.diagrams.render_sources import FIG_H, FIG_W, layout_boxes
    for key, b in layout_boxes().items():
        assert b["y"] >= 0, f"{key} extends below the canvas"
        assert b["y"] + b["h"] <= FIG_H, f"{key} extends above the canvas"
        assert b["x"] >= 0 and b["x"] + b["w"] <= FIG_W, f"{key} is off-canvas"


def test_sources_diagram_is_deterministic():
    from docs.diagrams.render_sources import render_svg
    assert render_svg() == render_svg()


def test_the_sources_svg_contains_no_timestamp():
    from docs.diagrams.render_sources import render_svg
    import re
    svg = render_svg()
    assert "dc:date" not in svg and "<dc:date>" not in svg
    assert not re.search(r"20\d\d-\d\d-\d\dT\d\d:", svg[:4000]), svg[:600]


# ==============================================================================
# grain_two_ways -- the plain-English figure (render_grain.py)
# ==============================================================================
# The other two figures describe the architecture. This one has to convince a reader
# who does not yet believe there is a problem, using one order, three rows and two
# hand-countable totals.
#
# That makes it the most dangerous of the three. A simplified example is exactly
# where a diagram starts rounding a date, inventing a fourth order, or quietly
# picking numbers that make the gap look bigger than it is. So every value in the
# figure is recomputed here from the committed data and from the compiler itself:
# the three orders, their legs, both small counts, and both headline percentages.

@pytest.fixture(scope="module")
def warehouse():
    from src import build_warehouse
    build_warehouse.build()
    from src.semantic.loader import load_semantic_model
    return load_semantic_model()


def _legs_of(order_id: str):
    """(promised_delivery_date, [(delivery_id, date)]) for one order.

    Read out of the standalone file's embedded CSVs rather than `data/*.csv`, because
    that is the copy the figure sits next to: the post's reader can only check the
    picture against the rows the post ships. The two agree on dates and disagree on leg
    ids -- the repo numbers legs sequentially, the embedded slice suffixes the split
    order A/B -- so reading the wrong one passes for the wrong reason.
    """
    import csv
    import io
    from datetime import date
    from src.semantic.constants import REPO_ROOT

    def d(s: str) -> date:
        y, m, dd = (int(p) for p in s.split("-"))
        return date(y, m, dd)

    demo = _load_standalone()
    orders = list(csv.DictReader(io.StringIO(demo.ORDERS_CSV)))
    legs = list(csv.DictReader(io.StringIO(demo.DELIVERY_LEGS_CSV)))
    assert REPO_ROOT.exists()
    order = next(r for r in orders if r["order_id"] == order_id)
    return d(order["promised_delivery_date"]), sorted(
        (r["delivery_id"], d(r["delivery_date"]))
        for r in legs if r["order_id"] == order_id)


def _load_standalone():
    """Import the single-file demo without running it. Cached on the function."""
    import importlib.util
    from src.semantic.constants import REPO_ROOT
    if getattr(_load_standalone, "_mod", None) is None:
        path = REPO_ROOT / "standalone" / "semantic_layer_demo.py"
        spec = importlib.util.spec_from_file_location("_sl_demo_for_diagram", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        _load_standalone._mod = module
    return _load_standalone._mod


def test_grain_committed_output_exists_and_is_nonempty():
    for name in ("grain_two_ways.svg", "grain_two_ways.png"):
        p = DIAGRAM_DIR / name
        assert p.exists(), f"missing {name}"
        assert p.stat().st_size > 5000, f"{name} looks truncated"


def test_grain_renderer_check_mode_says_committed_output_is_current():
    p = subprocess.run(
        [sys.executable, str(DIAGRAM_DIR / "render_grain.py"), "--check"],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert p.returncode == 0, (
        f"committed diagram is stale, run --write:\n{p.stdout}{p.stderr}")


def test_the_story_order_is_the_split_shipment_that_causes_the_gap():
    """SO-1009 is the whole figure. Every date and both notes come from the CSVs."""
    from docs.diagrams.render_grain import STORY
    promised, legs = _legs_of(STORY["order_id"])
    assert promised == STORY["promised"], (promised, STORY["promised"])
    assert len(legs) == 2, f"the story needs a two-leg order, this one has {legs}"
    assert legs == [(leg["id"], leg["date"]) for leg in STORY["legs"]], legs
    # The narrative claim: one leg beats the promise, the other misses it. Without
    # both halves the picture has no disagreement to draw.
    assert legs[0][1] <= promised < legs[1][1]
    for lid, dt in legs:
        note = next(leg["note"] for leg in STORY["legs"] if leg["id"] == lid)
        days = abs((dt - promised).days)
        assert note.startswith(str(days)), (
            f"{lid} is {days} days from the promise, the figure says {note!r}")


def test_the_three_orders_in_the_figure_are_real_rows():
    """No invented rows and no rounded dates -- the reader is invited to count these."""
    from docs.diagrams.render_grain import MINI
    for row in MINI:
        promised, legs = _legs_of(row["order"])
        assert promised == row["promised"], (row["order"], promised, row["promised"])
        assert legs == [(leg["leg"], leg["date"]) for leg in row["legs"]], (
            row["order"], legs)


def test_the_hand_countable_example_reproduces_the_real_disagreement():
    """2 of 3 against 3 of 4.

    The small example has to fail the same way the big one does, or it teaches the
    wrong lesson: the shipment-grain count must come out HIGHER, because that is why
    the wrong number survives review.
    """
    from docs.diagrams.render_grain import MINI, TOTALS, mini_counts
    counts = mini_counts()
    assert counts == {"order": (2, 3), "leg": (3, 4)}, counts
    by_order = 100.0 * counts["order"][0] / counts["order"][1]
    by_leg = 100.0 * counts["leg"][0] / counts["leg"][1]
    assert by_leg > by_order, "the illustration must overstate, like the real pair does"
    assert TOTALS["leg"]["pct"] > TOTALS["order"]["pct"], "and so must the headline pair"
    # Exactly one split order, or the example stops being about split shipments.
    assert sum(1 for r in MINI if len(r["legs"]) > 1) == 1


def test_the_headline_pair_is_what_the_two_queries_actually_return(warehouse):
    """48/55 and 54/61, from the compiler and from the naive delivery-grain join."""
    from datetime import date
    import duckdb
    from docs.diagrams.render_grain import TOTALS
    from src.semantic.compiler import compile_sql
    from src.semantic.constants import DATA_DIR, DB_PATH
    from src.semantic.executor import run
    from src.semantic.intent import Filter, QueryIntent, TimeWindow

    governed = run(compile_sql(QueryIntent(
        metric="on_time_delivery_pct", dimensions=[],
        filters=[Filter(column="region", operator="=", value="IN")],
        grain="order",
        time_window=TimeWindow(start=date(2026, 7, 1), end=date(2026, 7, 31),
                               label="July 2026"),
        intent_type="descriptive",
    ), warehouse))[0]
    assert (governed["numerator"], governed["denominator"]) == (
        TOTALS["order"]["num"], TOTALS["order"]["den"])
    assert round(governed["value"], 1) == TOTALS["order"]["pct"]

    con = duckdb.connect(str(DB_PATH), read_only=True)
    legs_csv = (DATA_DIR / "deliveries_raw.csv").as_posix()
    num, den = con.execute(
        "SELECT sum(CASE WHEN d.delivery_date <> '' "
        "                 AND CAST(d.delivery_date AS DATE) <= o.promised_delivery_date "
        "                THEN 1 ELSE 0 END), count(*) "
        "FROM fact_order_delivery o "
        f"JOIN read_csv_auto('{legs_csv}', header=true, all_varchar=true) d "
        "  ON d.order_id = o.order_id "
        "WHERE o.region='IN' AND o.is_eligible "
        "  AND o.promised_delivery_date BETWEEN DATE '2026-07-01' "
        "      AND DATE '2026-07-31'"
    ).fetchone()
    con.close()
    assert (num, den) == (TOTALS["leg"]["num"], TOTALS["leg"]["den"])
    assert round(100.0 * num / den, 1) == TOTALS["leg"]["pct"]
    gap = (100.0 * num / den) - governed["value"]
    assert abs(gap - TOTALS["gap_pp"]) < 0.005, (
        f"the figure prints a {TOTALS['gap_pp']} point gap; the queries differ "
        f"by {gap:.4f}")


def test_grain_layout_has_no_overlapping_panels():
    """Three of the first draft's defects were collisions -- the promise label through
    the step-1 heading, the step-2 heading through the left card, the metadata chip
    through the fix text. This holds the subset expressible as rectangles."""
    from docs.diagrams.render_grain import layout_boxes
    items = list(layout_boxes().items())
    for i, (ka, a) in enumerate(items):
        for kb, b in items[i + 1:]:
            separated = (
                a["y"] + a["h"] <= b["y"] + 1e-9 or b["y"] + b["h"] <= a["y"] + 1e-9
                or a["x"] + a["w"] <= b["x"] + 1e-9 or b["x"] + b["w"] <= a["x"] + 1e-9
            )
            assert separated, f"{ka} overlaps {kb}: {a} vs {b}"


def test_the_step_two_heading_sits_in_clear_space():
    """It belongs between band 1's floor and the cards' top. It was not, and the
    rendered PNG showed it printing through the left card's border."""
    from docs.diagrams.render_grain import BAND1, CARD_L, STEP2_Y
    top_of_cards = CARD_L["y"] + CARD_L["h"]
    assert top_of_cards + 0.12 < STEP2_Y < BAND1["y"] - 0.12, (
        f"step-2 heading at {STEP2_Y} is not inside "
        f"{top_of_cards:.2f}..{BAND1['y']:.2f}")


def test_grain_everything_fits_inside_the_figure():
    from docs.diagrams.render_grain import FIG_H, FIG_W, layout_boxes
    for key, b in layout_boxes().items():
        assert b["y"] >= 0, f"{key} extends below the canvas"
        assert b["y"] + b["h"] <= FIG_H, f"{key} extends above the canvas"
        assert b["x"] >= 0 and b["x"] + b["w"] <= FIG_W, f"{key} is off-canvas"


def test_grain_diagram_is_deterministic():
    from docs.diagrams.render_grain import render_svg
    assert render_svg() == render_svg()
