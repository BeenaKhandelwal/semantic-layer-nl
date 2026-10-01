"""Render the plain-English version of the whole problem: one order, two boxes, two answers.

The other two figures are for people who already accept the premise. `nl_dataflow.py` shows
which stage reads which artifact; `render_sources.py` shows where those artifacts come from.
Both assume you already believe that "grain" is a thing that can be wrong.

This one is for the reader who does not, and it has to land in about fifteen seconds:

    A courier splits one order into two boxes. The first arrives before the promised
    date. The second arrives after it. Was that order delivered on time?

There is no answer to that question in the database. There are two counting rules, both
defensible, and they disagree -- 87.3% against 88.5% over the same 55 orders. The picture
walks a reader from one concrete shipment, through a four-row hand-countable example, to the
two headline numbers, and ends on the single line of metadata that decides which is right.

Everything numeric here is real. `MINI` is three actual July orders from
the file the post embeds (`standalone/semantic_layer_demo.py`); `TOTALS` is the pair of figures the
compiler and the naive delivery-grain query produce. `tests/test_diagram.py` recomputes all
of it against the warehouse, so this figure cannot drift into a convenient illustration --
which matters more here than in the other two, because the simplified example is exactly
where a diagram would be tempted to lie.

    python docs/diagrams/render_grain.py --write    # regenerate SVG + PNG
    python docs/diagrams/render_grain.py --check    # fail if committed output is stale
"""
from __future__ import annotations

import io
import sys
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["svg.hashsalt"] = "semantic-layer-nl"
matplotlib.rcParams["svg.fonttype"] = "path"

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle  # noqa: E402

HERE = Path(__file__).resolve().parent
SVG_PATH = HERE / "grain_two_ways.svg"
PNG_PATH = HERE / "grain_two_ways.png"

# --------------------------------------------------------------------------------------
# palette -- green means "counted as on time", red means "counted as late". Nothing else
# in the figure uses those two colours, so the eye can follow one meaning.
# --------------------------------------------------------------------------------------

OK = {"fill": "#e8f5e9", "edge": "#2e7d32", "text": "#1b5e20"}
BAD = {"fill": "#fdecea", "edge": "#c0392b", "text": "#8c2318"}
NEUTRAL = {"fill": "#eef2f7", "edge": "#5a6470", "text": "#2c3844"}

INK = "#1a1a1a"
MUTED = "#5a6470"
NAVY = "#0f2942"
MONO = "DejaVu Sans Mono"

# --------------------------------------------------------------------------------------
# the content, as data -- every number below is asserted against the warehouse
# --------------------------------------------------------------------------------------

# Band 1: one real order, told as a story. SO-1009 is the order that costs you the number.
STORY = {
    "order_id": "SO-1009",
    "promised": date(2026, 7, 17),
    "legs": [
        {"id": "DL-1009A", "label": "Box 1 of 2", "date": date(2026, 7, 16),
         "note": "1 day early"},
        {"id": "DL-1009B", "label": "Box 2 of 2", "date": date(2026, 7, 20),
         "note": "3 days late"},
        # ids as they appear in the file the post embeds: the split order's legs are
        # suffixed A/B, single-leg orders are not.
    ],
    "plain": [
        "A customer ordered one thing and was promised it by 17 July.",
        "The warehouse shipped it in two boxes: one arrived early, one arrived late.",
        "The customer had a complete order on 20 July — three days after the promise.",
    ],
    "question": "So: was SO-1009 delivered on time?",
}

# Band 2: the same three real orders counted two ways. Small enough to check by hand,
# which is the entire point -- a reader who counts along has understood grain.
MINI = [
    {"order": "SO-1008", "promised": date(2026, 7, 16),
     "legs": [{"leg": "DL-1008", "date": date(2026, 7, 15)}]},
    {"order": "SO-1009", "promised": date(2026, 7, 17),
     "legs": [{"leg": "DL-1009A", "date": date(2026, 7, 16)},
              {"leg": "DL-1009B", "date": date(2026, 7, 20)}]},
    {"order": "SO-1011", "promised": date(2026, 7, 24),
     "legs": [{"leg": "DL-1011", "date": date(2026, 7, 21)}]},
]

# Band 3: the real headline pair, over the whole July India slice.
TOTALS = {
    "order": {"num": 48, "den": 55, "pct": 87.3,
              "rule": "one row per ORDER",
              "who": "the number the business signed off",
              "why": "an order is on time only when its LAST box arrives in time"},
    "leg": {"num": 54, "den": 61, "pct": 88.5,
            "rule": "one row per SHIPMENT",
            "who": "the number a text-to-SQL query returns",
            "why": "every box votes, so a split order votes twice"},
    "gap_pp": 1.25,
}

# Band 4: the fix, in the fewest words that are still true.
FIX = {
    "field": "grain: order",
    "lines": [
        "Nothing in the database says which counting rule is right — both queries are "
        "valid SQL, and both look reasonable in review.",
        "So a person writes the rule down once, in metadata, as the field above. Then a "
        "machine can check every question against it before it runs,",
        "and the query that counts one row per shipment is refused by name instead of "
        "being answered 1.25 points too high.",
    ],
}

NOTE = ("Every figure here is measured, not illustrative: the three orders are real rows, "
        "and 48/55 and 54/61 are what the two queries actually return.")


def on_time_by_order(row: dict) -> bool:
    """The declared rule: the order is on time when its LAST leg beats the promise."""
    return max(leg["date"] for leg in row["legs"]) <= row["promised"]


def mini_counts() -> dict[str, tuple[int, int]]:
    """(on time, total) at each grain, computed from MINI rather than typed in."""
    orders_ok = sum(1 for r in MINI if on_time_by_order(r))
    legs = [(leg, r) for r in MINI for leg in r["legs"]]
    legs_ok = sum(1 for leg, r in legs if leg["date"] <= r["promised"])
    return {"order": (orders_ok, len(MINI)), "leg": (legs_ok, len(legs))}


def _pct(num: int, den: int) -> str:
    return f"{100.0 * num / den:.1f}%"


# --------------------------------------------------------------------------------------
# layout
# --------------------------------------------------------------------------------------

# Every one of these numbers was moved at least once after looking at the rendered PNG.
# The first draft put the promise label through the step-1 heading, the step-2 heading
# through the left card, and the `grain: order` chip on top of the first line of the fix --
# none of which is visible in the code and all of which is obvious in the image. The gaps
# between bands are 0.28 or more, and `layout_boxes()` is what the overlap test checks.
FIG_W, FIG_H = 20.0, 12.9

BAND1 = {"x": 0.30, "y": 9.44, "w": 19.40, "h": 2.20}
CARD_L = {"x": 0.30, "y": 4.80, "w": 9.00, "h": 4.06}
CARD_R = {"x": 10.40, "y": 4.80, "w": 9.30, "h": 4.06}
BAND3 = {"x": 0.30, "y": 2.28, "w": 19.40, "h": 2.24}
BAND4 = {"x": 0.30, "y": 0.62, "w": 19.40, "h": 1.36}

STEP2_Y = 9.12   # in the 0.58 of clear space between band 1's floor and the cards' top

# The timeline inside band 1: 14 July .. 22 July mapped onto x.
TL_X0, TL_X1 = 1.35, 8.70
TL_D0, TL_D1 = date(2026, 7, 14), date(2026, 7, 22)
TL_Y = 9.94


def tl_x(d: date) -> float:
    span = (TL_D1 - TL_D0).days
    return TL_X0 + (TL_X1 - TL_X0) * ((d - TL_D0).days / span)


def layout_boxes() -> dict[str, dict[str, float]]:
    """The opaque panels, for the overlap test.

    The two cards are the pair that actually collided while this was being drawn -- the
    right card started at 9.60 and its border sat on top of the left card's totals row.
    """
    return {"band1:story": BAND1, "card:order": CARD_L, "card:leg": CARD_R,
            "band3:totals": BAND3, "band4:fix": BAND4}


def _panel(ax, box, fill="#ffffff", edge="#c7d0da", lw=1.4, zorder=1):
    ax.add_patch(FancyBboxPatch(
        (box["x"], box["y"]), box["w"], box["h"],
        boxstyle="round,pad=0.05,rounding_size=0.12",
        facecolor=fill, edgecolor=edge, linewidth=lw, zorder=zorder))


def _step_label(ax, x, y, n, text, sub=None):
    ax.add_patch(FancyBboxPatch(
        (x, y - 0.17), 0.40, 0.36,
        boxstyle="round,pad=0.02,rounding_size=0.07",
        facecolor=NAVY, edgecolor="none", zorder=3))
    ax.text(x + 0.20, y + 0.01, str(n), fontsize=11.4, fontweight="bold",
            color="white", ha="center", va="center", zorder=4)
    ax.text(x + 0.58, y + 0.02, text, fontsize=13.0, fontweight="bold",
            color=NAVY, va="center", zorder=3)
    if sub:
        ax.text(x + 0.58, y - 0.32, sub, fontsize=9.8, color=MUTED, va="center",
                zorder=3)


def _tick(verdict: bool) -> str:
    return "✓" if verdict else "✗"


def _build_figure():
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
    ax.set_xlim(0, FIG_W)
    ax.set_ylim(0, FIG_H)
    ax.axis("off")

    ax.text(0.30, 12.46, "One order, two boxes, two different “correct” answers",
            fontsize=23, fontweight="bold", color=NAVY, va="center")
    ax.text(0.30, 12.00,
            "Ask a computer “what was our on-time delivery last month?” in plain "
            "English and it can return either 87.3% or 88.5% from the same data. "
            "Here is where the two numbers come from.",
            fontsize=12.0, color=MUTED, va="center")

    # ---- band 1: the story ------------------------------------------------------
    _panel(ax, BAND1)
    _step_label(ax, BAND1["x"] + 0.22, BAND1["y"] + BAND1["h"] - 0.28,
                1, "What actually happened to one order")

    ax.plot([TL_X0 - 0.25, TL_X1 + 0.35], [TL_Y, TL_Y], color="#9aa7b4",
            linewidth=1.6, zorder=2)
    for d in (date(2026, 7, 14), date(2026, 7, 16), date(2026, 7, 18),
              date(2026, 7, 20), date(2026, 7, 22)):
        x = tl_x(d)
        ax.plot([x, x], [TL_Y - 0.07, TL_Y + 0.07], color="#9aa7b4", linewidth=1.4,
                zorder=2)
        ax.text(x, TL_Y - 0.26, d.strftime("%d %b"), fontsize=8.6, color=MUTED,
                ha="center", va="center", zorder=3)

    px = tl_x(STORY["promised"])
    ax.plot([px, px], [TL_Y - 0.14, TL_Y + 1.00], color="#7d6608", linewidth=1.8,
            linestyle=(0, (4, 2)), zorder=3)
    ax.text(px, TL_Y + 1.10, f"PROMISED  {STORY['promised'].strftime('%d %b')}",
            fontsize=9.4, fontweight="bold", color="#7d6608", ha="center", va="center",
            zorder=4)

    for leg in STORY["legs"]:
        early = leg["date"] <= STORY["promised"]
        c = OK if early else BAD
        x = tl_x(leg["date"])
        y = TL_Y + 0.30
        ax.add_patch(FancyBboxPatch(
            (x - 0.80, y), 1.60, 0.62,
            boxstyle="round,pad=0.03,rounding_size=0.08",
            facecolor=c["fill"], edgecolor=c["edge"], linewidth=1.5, zorder=4))
        ax.text(x, y + 0.42, f"{_tick(early)}  {leg['label']}", fontsize=9.6,
                fontweight="bold", color=c["text"], ha="center", va="center", zorder=5)
        ax.text(x, y + 0.18, f"{leg['date'].strftime('%d %b')} · {leg['note']}",
                fontsize=8.4, color=c["text"], ha="center", va="center", zorder=5)
        ax.add_patch(FancyArrowPatch(
            (x, y - 0.02), (x, TL_Y + 0.06), arrowstyle="-|>", mutation_scale=9,
            linewidth=1.1, color=c["edge"], alpha=0.7, zorder=3))

    for i, line in enumerate(STORY["plain"]):
        ax.text(10.10, BAND1["y"] + BAND1["h"] - 0.58 - i * 0.32, f"•  {line}",
                fontsize=10.6, color=INK, va="center", zorder=3)
    ax.text(10.10, BAND1["y"] + 0.30, STORY["question"], fontsize=11.8,
            fontweight="bold", color="#8c2318", va="center", zorder=3)
    ax.text(15.85, BAND1["y"] + 0.30,
            "Both answers below are defensible. That is the problem.",
            fontsize=9.8, color=MUTED, style="italic", va="center", zorder=3)

    # ---- band 2: the same three orders, counted two ways ------------------------
    counts = mini_counts()

    for side, card, palette in (("order", CARD_L, NEUTRAL), ("leg", CARD_R, NEUTRAL)):
        t = TOTALS[side]
        wrong = side == "leg"
        _panel(ax, card, edge=(BAD["edge"] if wrong else OK["edge"]), lw=1.8)

        head_y = card["y"] + card["h"] - 0.34
        ax.text(card["x"] + 0.28, head_y,
                f"Count {t['rule']}", fontsize=13.4, fontweight="bold",
                color=(BAD["text"] if wrong else OK["text"]), va="center", zorder=3)
        ax.text(card["x"] + 0.28, head_y - 0.36, t["why"], fontsize=10.0,
                color=MUTED, va="center", zorder=3)

        # column headers
        cy = head_y - 0.80
        cols = ([("Order", 0.30), ("Promised", 2.30), ("Last box arrived", 4.05),
                 ("On time?", 7.30)] if side == "order"
                else [("Order", 0.30), ("Box", 1.95), ("Promised", 4.00),
                      ("This box arrived", 5.60), ("On time?", 8.05)])
        for label, dx in cols:
            ax.text(card["x"] + dx, cy, label.upper(), fontsize=8.6, fontweight="bold",
                    color=MUTED, va="center", zorder=3)
        ax.plot([card["x"] + 0.28, card["x"] + card["w"] - 0.28], [cy - 0.16, cy - 0.16],
                color="#c7d0da", linewidth=1.1, zorder=2)

        # rows
        ry = cy - 0.50
        if side == "order":
            for row in MINI:
                ok = on_time_by_order(row)
                c = OK if ok else BAD
                last = max(leg["date"] for leg in row["legs"])
                split = len(row["legs"]) > 1
                ax.text(card["x"] + 0.30, ry, row["order"], fontsize=10.2,
                        family=MONO, color=INK, va="center", zorder=3)
                ax.text(card["x"] + 2.30, ry, row["promised"].strftime("%d %b"),
                        fontsize=10.0, color=MUTED, va="center", zorder=3)
                ax.text(card["x"] + 4.05, ry,
                        last.strftime("%d %b") + ("   (of 2 boxes)" if split else ""),
                        fontsize=10.0, color=MUTED, va="center", zorder=3)
                ax.text(card["x"] + 7.30, ry, f"{_tick(ok)}  {'yes' if ok else 'no'}",
                        fontsize=10.4, fontweight="bold", color=c["text"], va="center",
                        zorder=3)
                ry -= 0.44
        else:
            for row in MINI:
                for j, leg in enumerate(row["legs"]):
                    ok = leg["date"] <= row["promised"]
                    c = OK if ok else BAD
                    ax.text(card["x"] + 0.30, ry, row["order"], fontsize=10.2,
                            family=MONO, color=INK, va="center", zorder=3)
                    ax.text(card["x"] + 1.95, ry, leg["leg"], fontsize=10.2,
                            family=MONO, color=MUTED, va="center", zorder=3)
                    ax.text(card["x"] + 4.00, ry, row["promised"].strftime("%d %b"),
                            fontsize=10.0, color=MUTED, va="center", zorder=3)
                    ax.text(card["x"] + 5.60, ry, leg["date"].strftime("%d %b"),
                            fontsize=10.0, color=MUTED, va="center", zorder=3)
                    ax.text(card["x"] + 8.05, ry, f"{_tick(ok)}  {'yes' if ok else 'no'}",
                            fontsize=10.4, fontweight="bold", color=c["text"],
                            va="center", zorder=3)
                    if len(row["legs"]) > 1:
                        ax.text(card["x"] + 6.85, ry, "same order",
                                fontsize=8.2, color=BAD["text"], style="italic",
                                va="center", zorder=3)
                    ry -= 0.44
                    del j

        # the count for this card
        ok_n, total_n = counts[side]
        strip_y = card["y"] + 0.24
        ax.add_patch(Rectangle((card["x"] + 0.28, strip_y), card["w"] - 0.56, 0.58,
                               facecolor=(BAD["fill"] if wrong else OK["fill"]),
                               edgecolor="none", zorder=2))
        ax.text(card["x"] + 0.44, strip_y + 0.29,
                f"{ok_n} of {total_n} on time  =  {_pct(ok_n, total_n)}",
                fontsize=12.6, fontweight="bold",
                color=(BAD["text"] if wrong else OK["text"]), va="center", zorder=3)
        ax.text(card["x"] + card["w"] - 0.44, strip_y + 0.29,
                "count by hand — it is only three orders", fontsize=9.0,
                color=MUTED, ha="right", va="center", style="italic", zorder=3)

    _step_label(ax, CARD_L["x"] + 0.22, STEP2_Y,
                2, "Three real orders, counted two ways")
    ax.text(6.65, STEP2_Y, "one of them shipped in two boxes — that is the only "
            "difference between the two answers", fontsize=9.8, color=MUTED,
            va="center", zorder=3)
    ax.text(9.85, CARD_L["y"] + CARD_L["h"] / 2, "≠", fontsize=30,
            fontweight="bold", color="#8c2318", ha="center", va="center", zorder=5)

    # ---- band 3: the real numbers ----------------------------------------------
    _panel(ax, BAND3, fill="#fbfcfd")
    _step_label(ax, BAND3["x"] + 0.22, BAND3["y"] + BAND3["h"] - 0.30,
                3, "Now do the same over all 55 orders",
                sub="61 shipments, July 2026, India — the sample the article ships")

    for side, x in (("order", 0.72), ("leg", 10.20)):
        t = TOTALS[side]
        wrong = side == "leg"
        c = BAD if wrong else OK
        ax.text(x, BAND3["y"] + 0.86, f"{t['pct']:.1f}%", fontsize=30,
                fontweight="bold", color=c["text"], va="center", zorder=3)
        ax.text(x + 2.30, BAND3["y"] + 1.00, f"{t['num']} of {t['den']} {side}s on time",
                fontsize=11.0, color=INK, va="center", zorder=3)
        ax.text(x + 2.30, BAND3["y"] + 0.66, t["who"], fontsize=10.4,
                color=c["text"], fontweight="bold", va="center", zorder=3)
        ax.text(x + 2.30, BAND3["y"] + 0.34, f"counted {t['rule'].lower()}",
                fontsize=9.6, color=MUTED, va="center", zorder=3)

    ax.add_patch(FancyBboxPatch(
        (7.62, BAND3["y"] + 0.42), 2.10, 0.92,
        boxstyle="round,pad=0.04,rounding_size=0.10",
        facecolor="#fffdf5", edgecolor="#d6c98a", linewidth=1.5, zorder=3))
    ax.text(8.67, BAND3["y"] + 1.06, f"{TOTALS['gap_pp']:.2f} points", fontsize=11.6,
            fontweight="bold", color="#7d6608", ha="center", va="center", zorder=4)
    ax.text(8.67, BAND3["y"] + 0.70, "apart, and the\nwrong one is higher", fontsize=8.8,
            color="#7d6608", ha="center", va="center", linespacing=1.4, zorder=4)

    # ---- band 4: the fix -------------------------------------------------------
    _panel(ax, BAND4, fill="#f3f0fa", edge="#7e57c2", lw=1.6)
    head_y = BAND4["y"] + BAND4["h"] - 0.34
    ax.text(BAND4["x"] + 0.30, head_y,
            "The whole fix is one line of metadata:", fontsize=11.4,
            fontweight="bold", color="#4527a0", va="center", zorder=3)
    ax.add_patch(FancyBboxPatch(
        (BAND4["x"] + 5.10, head_y - 0.20), 2.10, 0.40,
        boxstyle="round,pad=0.02,rounding_size=0.06",
        facecolor="white", edgecolor="#7e57c2", linewidth=1.4, zorder=3))
    ax.text(BAND4["x"] + 6.15, head_y, FIX["field"],
            fontsize=11.0, family=MONO, fontweight="bold", color="#4527a0",
            ha="center", va="center", zorder=4)
    for i, line in enumerate(FIX["lines"]):
        ax.text(BAND4["x"] + 0.30, head_y - 0.38 - i * 0.25, line,
                fontsize=9.4, color="#3b3b46", va="center", zorder=3)

    ax.text(FIG_W - 0.30, 0.30, NOTE, fontsize=8.6, color=MUTED, ha="right",
            va="center", style="italic", zorder=3)

    return fig


# --------------------------------------------------------------------------------------
# output -- identical contract to the other two renderers
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
        print("\nRegenerate with: python docs/diagrams/render_grain.py --write")
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
