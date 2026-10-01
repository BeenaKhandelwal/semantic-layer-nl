# Medium publication kit

**87.3% or 88.5%? Your LLM Can't Tell — and It Will Pick the Flattering One**

Everything needed to publish, in reading order. Generated from `content/medium-post.md` by `content/build_medium_kit.py` — regenerate rather than edit, or the copy here stops matching the copy under test.

## What is in this document

- **Part 1 — The article, as it will be published.** Prose, code excerpts, real console output, and both figures. The one thing lifted out is the complete source file, which is too long to sit inside a document meant for editing.
- **Part 2 — The publishing checklist.** Title and subtitle slots, tags, which figure goes where, the canonical-URL decision, sequencing against the two LinkedIn pieces, and what to cut if it runs long.

## The companion file

`medium-code.pdf` carries the complete runnable file — 1056 lines, sha256 `271b0e57c611`. Publish it as a Gist and link it from the article; PDFs and copy-paste do not mix.

## Before publishing

Every figure in Part 1 is measured against a warehouse built from the committed CSVs at a frozen as-of date of **2026-08-07**. The console output is a real run, spliced in by the build, not transcribed. To confirm both before you publish:

```bash
python content/build_medium_post.py --check
python content/build_medium_kit.py --check
python -m pytest tests/test_content.py tests/test_standalone.py -q
```

*Article source: `content/medium-post.md` (1925 lines).*

<div style="page-break-before: always;"></div>

# Part 1 — The article, as it will be published

*The two lines marked TITLE and SUBTITLE go in Medium's title and subtitle slots, not in the body.*

## TITLE — 87.3% or 88.5%? Your LLM Can't Tell — and It Will Pick the Flattering One

### SUBTITLE — A governed semantic layer that refuses the wrong number — complete, executable Python, two dependencies, no API key.

![One order shipped in two boxes, counted two ways: 87.3% and 88.5% from the same rows](../docs/diagrams/grain_two_ways.svg)

*The entire argument in one picture. A courier splits one order into two boxes; the two
defensible ways to count that order disagree, and the disagreement scales to the whole
month. Every figure in it is measured from the data the code below ships — a test
recomputes all of them, including the three-order example. The full-resolution original is
`docs/diagrams/grain_two_ways.svg` in the repository linked at the end.*

Two numbers came out of the same DuckDB file on the same afternoon, from the same
question:

> *"On-time delivery for India warehouses last month."*

**88.5%** and **87.3%**. One of them is wrong, and in the review nobody could say which.

That last part is the actual problem, and prompt engineering cannot reach it.

---

## Start here: one order, two boxes

*If `grain` and `fan-out` are words you already use at work, skip to **The rule everything
else follows from**. Nothing in this section is needed twice.*

A customer orders one thing and is promised it by **17 July**. The warehouse ships it in
two boxes:

- **Box 1** arrives **16 July** — one day early.
- **Box 2** arrives **20 July** — three days late.

The customer had a complete order on 20 July. So: *was that order delivered on time?*

Nothing in the database answers that question. There are two counting rules, and both are
defensible:

- **One row per order.** An order is on time only when its *last* box arrives in time. By
  this rule the order is **late**.
- **One row per shipment.** Every box is counted on its own. By this rule the order is
  **one box on time and one box late**.

Pick either. Just notice that nobody has written down which one the company means.

### Count three real orders by hand

These are three actual orders out of the data the code below ships. Two arrived in a single
box; `SO-1009` is the one that shipped in two:

| Order | Promised | Boxes | Last box arrived | On time, counting orders? |
|---|---|---|---|---|
| `SO-1008` | 16 Jul | 1 | 15 Jul | yes |
| `SO-1009` | 17 Jul | 2 | 20 Jul | **no** |
| `SO-1011` | 24 Jul | 1 | 21 Jul | yes |

Counting **orders**, two of the three were on time — **66.7%**.

Counting **shipments** there are four rows rather than three, because `SO-1009` contributes
two: its first box beat the promise and its second missed it. Three of four — **75.0%**.

Same three orders, same dates, two answers — and the higher one came from the rule nobody
had written down. Across the full month, 55 orders arriving in 61 shipments, those same two
rules give **87.3%** and **88.5%**.

### Five words the rest of this post needs

| Word | What it means here |
|---|---|
| **grain** | What one row of a table stands for. The orders table's grain is one row per order; the delivery table's is one row per *shipment*. Almost nothing in a database records this. |
| **fan-out** | What happens when you join a table to a finer-grained one: one order becomes two rows, and gets counted twice. That is the 88.5%. |
| **metric** | A number with its definition written down — numerator, denominator, grain, which rows to exclude, and a named person who approved it. |
| **gate** | A check that runs *before* the query does and refuses it if something the metric declared is not satisfied. |
| **provenance** | The record of how one answer was produced: which metric, which arithmetic, which rows, which checks passed. |

Everything below is those five ideas as a single Python file you can run.

---

**TL;DR** — Natural-language querying does not fail on SQL syntax. It fails on *grain*:
the model writes a valid query against a table whose row meaning nobody wrote down. The
fix is architectural — the model picks a governed metric and emits validated JSON, a
deterministic compiler writes the SQL, and seven gates run in between. And once that
metadata exists, the same file answers the question no BI tool can take — *why* the number
dropped — by attributing each late order to a manufacturing phase. This post is that system
as a single file you can paste into a terminal.

**You will need** Python 3.10 or newer and two packages. No credentials, no network, no
warehouse of your own.

```bash
pip install duckdb pyyaml
python semantic_layer_demo.py
```

**In this post**

- Plain English first: one order, two boxes, and the five words that follow
- Where the wrong number comes from: six split shipments
- The metadata fields that decide correctness, and why no crawler emits them
- The one word in the warehouse build that changes the answer
- The seven gates, including the one that refuses the wrong query by name
- Why on-time delivery dropped — the diagnostic question BI tools cannot take
- The complete file, verbatim

*New to this? The first section needs no SQL. Only have five minutes? Read **the seven
gates** and **why it dropped** — that pair is the argument.*

---

## Where the wrong number comes from

The delivery table has one row per delivery *leg*. An order that ships in two legs —
partial shipment on Tuesday, remainder on Friday — has two rows.

Join orders to legs and count, and that order votes twice. Worse: if the first leg
arrived before the promised date, the order looks on time twice over, while the second
leg that actually blew the promise is one row among 61.

- Order grain: **48 / 55 = 87.27%**
- Delivery grain: **54 / 61 = 88.52%**

The gap is 1.25 points. Small enough to look like rounding, and it always errs upward.

> A wrong number that flatters you is the one that survives to the board deck.

The model did not hallucinate. It wrote syntactically valid, semantically reasonable SQL
against a table whose grain nobody had written down anywhere it could read. **The failure
was in the metadata, so the fix has to be in the metadata.**

---

## The rule everything else follows from

> **The model never writes SQL and never does arithmetic.** It reads a governed metadata
> slice and emits a validated JSON object — which metric, which filters, which time
> window. A deterministic compiler turns that object into SQL.

Text-to-SQL asks a language model to be right about grain, joins, exclusions and fiscal
calendars on every single call. This asks it to be right about *one* much easier thing:
which approved metric you meant.

The pipeline is six stages, and only one of them touches a model:

```
retriever → resolver → validator → compiler → executor → provenance
              ↑            ↑
         the only        seven gates, before
         model call      any SQL exists
```

![The six stages of a governed natural-language query, and the metadata each one reads](../docs/diagrams/nl_dataflow.svg)

*Every arrow is one stage reading one artifact for one reason. The figure is generated from
the code it describes, so it cannot drift from the pipeline it depicts. The full-resolution
original is `docs/diagrams/nl_dataflow.svg` in the repository.*

Two users asking the same question in different words get the same number, because the
number was never in the model's hands.

---

## The data, and the one difference that matters

Two tables. `orders` has one row per customer order; `delivery_legs` has one row per
physical shipment. Six of the July orders shipped in two legs — those six are the entire
disagreement between 87.3% and 88.5%:

```
DL-1009A,SO-1009,1,2026-07-16
DL-1009B,SO-1009,2,2026-07-20
DL-1010,SO-1010,1,2026-07-22
DL-1011,SO-1011,1,2026-07-21
DL-1012A,SO-1012,1,2026-07-18
DL-1012B,SO-1012,2,2026-07-18
DL-1014A,SO-1014,1,2026-07-19
DL-1014B,SO-1014,2,2026-07-19
DL-1015,SO-1015,1,2026-07-19
DL-1016A,SO-1016,1,2026-07-21
DL-1016B,SO-1016,2,2026-07-21
DL-1017A,SO-1017,1,2026-07-22
DL-1017B,SO-1017,2,2026-07-22
DL-1018A,SO-1018,1,2026-07-23
DL-1018B,SO-1018,2,2026-07-23
```

`SO-1009` is the one that costs you the number. It was promised 2026-07-17. Its first leg
landed 07-16 — on time — and its second landed 07-20. At order grain it is late. At
delivery grain it is one hit and one miss, and the hit came first.

The file embeds the June and July 2026 India slice of the full project: 83 orders, 87
delivery legs, verbatim. That is the whole population behind every figure in this post, so
the numbers reproduce exactly rather than approximately.

---

## The metadata: the fields no crawler emits

Read this and ask which fields a catalog pointed at the warehouse could have produced:

```yaml
  - name: on_time_delivery_pct
    label: On-Time Delivery %
    description: >
      Share of eligible customer orders delivered on or before the promised delivery
      date. An order counts as delivered only when its final leg arrives.
    entity: fact_order_delivery
    grain: order
    time_dimension: promised_delivery_date
    expression:
      type: ratio_percent
      numerator: "sum(CASE WHEN is_on_time THEN 1 ELSE 0 END)"
      denominator: "sum(CASE WHEN is_eligible THEN 1 ELSE 0 END)"
    exclusions:
      - key: cancelled_orders
        predicate: "order_status <> 'CANC'"
        rationale: A cancelled order was never due; including it inflates the denominator.
      - key: not_yet_due
        predicate: "promised_delivery_date <= DATE '__AS_OF_DATE__'"
        rationale: >
          An order promised after the as-of date is not late, it is pending. Counting it
          as a miss understates performance.
    business_rules:
      - Measured against the CURRENT promised date, not the original.
      - Order-grain only. Delivery-grain aggregation double-counts split shipments.
    owner: VP Supply Chain
    approval_state: approved
    lineage: [SAP SD, SAP EWM, SAP TM, fact_order_delivery]
```

`entity` and `time_dimension`, maybe. **Not `grain`. Not `exclusions`. Not
`business_rules`. Not `approval_state`.** Those are decisions, made by a named human, and
they are exactly the fields that decide whether an answer is right rather than merely
well-formed.

Four things worth noticing, because each one is a defect that would otherwise ship:

1. **`grain: order`** is declared, not inferred. This is the field that kills 88.5%.
2. **Exclusions carry a `rationale`.** Six months on, an exclusion without a stated reason
   gets deleted by someone who assumes it was a mistake.
3. **`approval_state`** is read before the model sees anything. The second metric in the
   file is `draft`, so the retriever never offers it — it cannot be asked for because it
   was never on the menu.
4. **The ratio is declared as a numerator and a denominator**, never as a pre-averaged
   rate. The compiler sums numerators and sums denominators, then divides. Averaging
   percentages across groups of unequal size gives a different, wrong number, and it looks
   completely fine.

The one-to-many join is declared too, which is what lets a gate see the fan-out coming:

```yaml
entities:
  - name: fact_order_delivery
    grain: order                 # one row per order_id -- the load-bearing declaration
    primary_key: order_id
    joins:
      - to: raw_delivery_legs
        on: order_id
        cardinality: one_to_many # this is the hop that turns 87.27% into 88.52%

  - name: raw_delivery_legs
    grain: delivery
    primary_key: delivery_id
```

Which is the part that gets underestimated on a plan. In the full nine-artifact project,
exactly one artifact is machine-harvestable — the technical metadata harvested from the SAP
data dictionary. Everything else is derived from earlier artifacts, or authored by someone
accountable for the decision:

![Where each metadata artifact comes from, and when the pipeline consumes it](../docs/diagrams/metadata_sources.svg)

*Colour is provenance: harvested, derived, authored. A harvester gets you tables, fields,
domains and types. It cannot get you grain, exclusions, an approved definition or a standard
duration. The full-resolution original is `docs/diagrams/metadata_sources.svg` in the same
repository.*

---

## The warehouse: one word decides the answer

```python
def build_warehouse() -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB. The one interesting line is the aggregation to ORDER grain.

    `final_delivery_date = max(delivery_date)` is what "an order counts as delivered only
    when its final leg arrives" means in SQL. Taking min() -- or joining without
    aggregating at all -- is the 88.5% bug, and it is a one-word difference.
    """
    con = duckdb.connect(":memory:")
    variance_cols = PHASE_VARIANCE_CSV.splitlines()[0].split(",")[1:]
    for name, ddl, csv_text in (
        ("raw_orders",
         "order_id VARCHAR, region VARCHAR, plant VARCHAR, carrier VARCHAR, "
         "promised_delivery_date DATE, order_status VARCHAR", ORDERS_CSV),
        ("raw_delivery_legs",
         "delivery_id VARCHAR, order_id VARCHAR, delivery_leg INTEGER, "
         "delivery_date DATE", DELIVERY_LEGS_CSV),
        ("raw_phase_variance",
         "order_id VARCHAR, " + ", ".join(f"{c} INTEGER" for c in variance_cols),
         PHASE_VARIANCE_CSV),
    ):
        _load(con, name, ddl, csv_text)

    con.execute(f"""
        CREATE TABLE fact_order_delivery AS
        WITH final_leg AS (
            SELECT order_id,
                   max(delivery_date) AS final_delivery_date,
                   count(*)           AS delivery_count
            FROM raw_delivery_legs
            GROUP BY order_id                      -- <-- collapse to one row per ORDER
        )
        SELECT o.order_id, o.region, o.plant, o.carrier,
               o.promised_delivery_date, o.order_status,
               f.final_delivery_date,
               coalesce(f.delivery_count, 0) AS delivery_count,
               -- The two exclusions, materialised as a single eligibility flag.
               (o.order_status <> 'CANC'
                AND o.promised_delivery_date <= DATE '{AS_OF_DATE}') AS is_eligible,
               (f.final_delivery_date IS NOT NULL
                AND f.final_delivery_date <= o.promised_delivery_date) AS is_on_time
        FROM raw_orders o
        LEFT JOIN final_leg f USING (order_id)
    """)
    return con
```

`max(delivery_date)` is what *"an order counts as delivered only when its final leg
arrives"* means in SQL. Taking `min()` — or joining without aggregating at all — is the
88.5% bug, and it is a one-word difference in a query nobody would flag in review.

---

## The intent: the only thing the model is allowed to produce

```python
@dataclass(frozen=True)
class QueryIntent:
    """What a language model is permitted to emit. Note what is NOT in here: no SQL, no
    column expressions, no arithmetic, no join instructions. Every field is a reference
    to something the metadata already declares, which is what makes it checkable."""
    intent_type: str                       # descriptive | diagnostic
    metric: str
    grain: str
    time_window: tuple[str, str]
    time_label: str = ""
    dimensions: tuple[str, ...] = ()
    filters: tuple[Filter, ...] = ()
    compare_to: tuple[str, str] | None = None
    compare_label: str = ""

    def to_json(self) -> str:
        return json.dumps({
            "intent_type": self.intent_type, "metric": self.metric, "grain": self.grain,
            "time_window": list(self.time_window), "dimensions": list(self.dimensions),
            "filters": [{"column": f.column, "operator": f.operator, "value": f.value}
                        for f in self.filters],
        }, indent=2)
```

Note what is *not* in there: no SQL, no column expressions, no arithmetic, no join
instructions. Every field is a reference to something the metadata already declares, which
is precisely what makes it checkable by a machine before it runs.

---

## The resolver: the only stage that calls a model

The demo ships an offline keyword resolver so it runs with no credentials. The real one is
this, and the two are interchangeable by design — every stage downstream takes a
`QueryIntent` and cannot tell which produced it:

```python
def resolve_with_claude(question: str, model: dict) -> QueryIntent:   # pragma: no cover
    """The real resolver. Not called by `main` -- shown because it is the whole point.

    Two things make this safe, and neither is prompt wording. First, the retriever hands
    over only APPROVED metrics, so an unapproved one cannot be picked: it was never
    offered. Second, whatever comes back goes through all seven gates before it can
    become SQL, so a wrong intent is refused rather than answered.
    """
    import anthropic

    approved = [m for m in model["metrics"] if m["approval_state"] == "approved"]
    slice_for_model = {
        "metrics": [{k: m[k] for k in ("name", "label", "grain", "description")
                     if k in m} for m in approved],
        "dimensions": [{"name": d["name"], "allowed_values": d.get("allowed_values")}
                       for d in model["dimensions"]],
        "glossary": [{"term": t["term"], "metric": t["metric"],
                      "synonyms": t["synonyms"]} for t in model["glossary"]],
    }
    tool = {
        "name": "emit_query_intent",
        "description": "Emit the governed query intent for this question.",
        "input_schema": {
            "type": "object",
            "properties": {
                "intent_type": {"enum": ["descriptive", "diagnostic"]},
                "metric": {"enum": [m["name"] for m in approved]},
                "grain": {"type": "string"},
                "time_window": {"type": "array", "items": {"type": "string"},
                                "minItems": 2, "maxItems": 2},
                "dimensions": {"type": "array", "items": {"type": "string"}},
                "filters": {"type": "array", "items": {
                    "type": "object",
                    "properties": {"column": {"type": "string"},
                                   "operator": {"enum": ["=", "in", "between",
                                                         ">=", "<="]},
                                   "value": {}},
                    "required": ["column", "operator", "value"]}},
            },
            "required": ["intent_type", "metric", "grain", "time_window"],
        },
    }
    reply = anthropic.Anthropic().messages.create(
        model="claude-sonnet-5",
        max_tokens=1024,
        system=RESOLVER_SYSTEM_PROMPT,
        tools=[tool],
        tool_choice={"type": "tool", "name": "emit_query_intent"},
        messages=[{"role": "user", "content":
                   f"Metadata slice:\n{json.dumps(slice_for_model, indent=2)}\n\n"
                   f"Question: {question}"}],
    )
    args = next(b.input for b in reply.content if b.type == "tool_use")
    return QueryIntent(
        intent_type=args["intent_type"], metric=args["metric"], grain=args["grain"],
        time_window=tuple(args["time_window"]),
        dimensions=tuple(args.get("dimensions", ())),
        filters=tuple(Filter(f["column"], f["operator"], f["value"])
                      for f in args.get("filters", ())),
    )
```

Two things make this safe, and neither of them is prompt wording.

**The menu is filtered before the model sees it.** `approved` excludes the draft metric, so
the tool's `enum` cannot contain it. An unapproved metric is unaskable because it was never
offered — not because a gate would have caught it afterwards.

**Whatever comes back is still validated.** The system prompt matters less than the fact
that a wrong intent gets refused rather than answered:

```
You select a governed metric. You do not write SQL and you do not do arithmetic.

Return ONLY a QueryIntent. Every value must come from the metadata slice provided:
- metric: an exact name from the approved metric list
- grain:  the metric's declared grain, copied verbatim, never inferred from the question
- filters: only columns listed as dimensions, only values from allowed_values
- time_window: explicit start and end dates, never open-ended

If the question cannot be answered from this slice, say so instead of approximating.
An approximation that looks like an answer is worse than a refusal.
```

---

## The validator: seven gates, and they fail closed

```python
GATE_NAMES = ("metric_approved", "dimensions_declared", "filters_bound", "grain_matches",
              "no_fanout", "time_window_bounded", "exclusions_applied")


@dataclass
class ValidationResult:
    passed: dict[str, bool] = field(default_factory=dict)
    failures: list[tuple[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.passed) == len(GATE_NAMES) and all(self.passed.values())


def validate(qi: QueryIntent, model: dict) -> ValidationResult:
    """Never raises. A hallucinated metric name is a normal, expected input."""
    r = ValidationResult()
    metric = get_metric(model, qi.metric)

    def gate(name: str, ok: bool, why: str = "") -> None:
        r.passed[name] = ok
        if not ok:
            r.failures.append((name, why))

    gate("metric_approved",
         metric is not None and metric.get("approval_state") == "approved",
         f"Metric {qi.metric!r} is not an approved metric. Approved: "
         + ", ".join(m["name"] for m in model["metrics"]
                     if m["approval_state"] == "approved"))

    undeclared = [d for d in qi.dimensions if d not in model["_dims_by_name"]]
    gate("dimensions_declared", not undeclared,
         f"Dimensions {undeclared} are not declared in the semantic model.")

    unbound = [f.column for f in qi.filters if f.column not in model["_dims_by_name"]]
    outside = [f"{f.column}={f.value!r}" for f in qi.filters
               if f.column in model["_dims_by_name"]
               and model["_dims_by_name"][f.column].get("allowed_values")
               and f.value not in model["_dims_by_name"][f.column]["allowed_values"]]
    gate("filters_bound", not unbound and not outside,
         f"Filter columns {unbound} do not bind to a declared dimension."
         if unbound else
         f"Filter {', '.join(outside)} is outside the declared allowed_values. Without "
         f"this gate the query returns zero rows, and zero rows gets read as an answer.")

    if metric is None:
        gate("grain_matches", False,
             f"Cannot check grain: metric {qi.metric!r} is not in the semantic model, so "
             f"there is no certified grain to compare {qi.grain!r} against.")
    else:
        gate("grain_matches", qi.grain == metric["grain"],
             f"Metric {qi.metric!r} is certified at grain {metric['grain']!r}; the intent "
             f"asks for grain {qi.grain!r}. Aggregating at the wrong grain changes the "
             f"number.")

    fanout = []
    if metric is not None:
        home = metric["entity"]
        for name in list(qi.dimensions) + [f.column for f in qi.filters]:
            dim = model["_dims_by_name"].get(name)
            if dim is None or dim["entity"] == home:
                continue
            join = next((j for j in model["_entities_by_name"][home].get("joins", [])
                         if j["to"] == dim["entity"]), None)
            # A many_to_one hop cannot duplicate rows and must pass. Only one_to_many
            # fans out. A gate that blocked every join would look correct and quietly
            # break every legitimate cross-entity question.
            if join is None or join["cardinality"] == "one_to_many":
                fanout.append(f"{name} (on {dim['entity']})")
    gate("no_fanout", not fanout,
         f"Reaching {', '.join(fanout)} requires a one_to_many join, which duplicates "
         f"rows before aggregation.")

    start, end = qi.time_window
    gate("time_window_bounded", bool(start and end) and start <= end,
         f"Time window {qi.time_window} is unbounded or inverted.")

    gate("exclusions_applied",
         metric is not None and all(e.get("predicate") for e in
                                    metric.get("exclusions", [])),
         f"Metric {qi.metric!r} declares an exclusion with no predicate, so it cannot be "
         f"applied. A metric whose exclusions cannot be enforced must not be answered.")
    return r
```

Three rules in there are worth stating out loud.

**All seven gates always run.** Not "until the first failure" — a user asking a
badly-formed question deserves every reason at once, not a game of whack-a-mole.

**A gate that cannot be evaluated fails closed.** Look at `grain_matches` when the metric
does not exist: it reports a failure explaining that there is no certified grain to compare
against. The tempting alternative is to skip it.

> *"I did not check"* recorded as *"I checked and it was fine"* is the single most dangerous
> line you can write in a governance layer.

**`no_fanout` blocks only `one_to_many`.** A `many_to_one` hop cannot duplicate rows, so
refusing every join would look correct and quietly break every legitimate cross-entity
question. Gates that are too strict get switched off, and a switched-off gate protects
nothing.

And validation runs **before** compilation, so a refused question never becomes SQL:

```python
def answer(con, qi: QueryIntent, model: dict) -> tuple[int, str]:
    """Validate, then compile. Never the other way round.

    The refusal is the feature. "I cannot answer that, and here is which rule stopped me"
    is a system you can put in front of a CFO. One that always produces a number is not.
    """
    result = validate(qi, model)
    if not result.ok:
        lines = [f"REFUSED  {qi.metric}: the intent did not pass validation.", "",
                 "  gates failed  " + ", ".join(g for g, ok in sorted(result.passed.items())
                                                if not ok)]
        for gate_name, why in result.failures:
            lines += _wrap(gate_name, why)
        lines += ["",
                  "  No number is shown. A value that failed a gate is not a caveated",
                  "  answer, it is an unverified one."]
        return 1, "\n".join(lines)

    ans = execute(con, qi, model)
    ans.gates = result.passed
    out = [ans.render()]
    if qi.intent_type == "diagnostic":
        out.append(_diagnose(con, qi, model, ans))
    return 0, "\n\n".join(out)
```

---

## The compiler: the only thing that writes SQL

```python
def compile_sql(qi: QueryIntent, model: dict,
                window: tuple[str, str] | None = None) -> str:
    """Deterministic. Same intent in, same SQL out, byte for byte.

    Ratios are compiled as `sum(numerator) / sum(denominator)`, never as an average of
    per-group rates. Averaging rates across groups of unequal size gives a different
    number -- Simpson's paradox -- and no amount of prompting reliably prevents a model
    from doing it. Here it is structurally impossible.
    """
    metric = get_metric(model, qi.metric)
    start, end = window or qi.time_window
    expr = metric["expression"]

    where = [f"{metric['time_dimension']} BETWEEN DATE '{start}' AND DATE '{end}'"]
    where += [e["predicate"] for e in metric.get("exclusions", [])]   # unconditional
    for f in qi.filters:
        col = model["_dims_by_name"][f.column]["column"]
        where.append(f"{col} {f.operator} '{f.value}'")

    group = [model["_dims_by_name"][d]["column"] for d in qi.dimensions]
    select = group + [
        f"round(100.0 * {expr['numerator']} / nullif({expr['denominator']}, 0), 4) "
        f"AS value",
        f"{expr['numerator']} AS numerator",
        f"{expr['denominator']} AS denominator",
    ]
    sql = (f"SELECT {', '.join(select)}\nFROM {metric['entity']}\n"
           f"WHERE {(chr(10) + '  AND ').join(where)}")
    if group:
        sql += f"\nGROUP BY {', '.join(group)}\nORDER BY {', '.join(group)}"
    return sql
```

Two properties, both structural rather than hoped-for. The exclusions are appended
unconditionally — no branch on what the question asked, so a question that mentions neither
cancellations nor due dates still excludes both. And the ratio is compiled as
`sum(numerator) / sum(denominator)`, so averaging rates across unequal groups is not a
mistake this code is capable of making.

---

## Running it

### The governed answer

```
1. THE GOVERNED ANSWER
   What was OTD for India warehouses last month?
==============================================================================


The resolver emitted this, and nothing else:
{
  "intent_type": "descriptive",
  "metric": "on_time_delivery_pct",
  "grain": "order",
  "time_window": [
    "2026-07-01",
    "2026-07-31"
  ],
  "dimensions": [],
  "filters": [
    {
      "column": "region",
      "operator": "=",
      "value": "IN"
    }
  ]
}

Note `grain` came from the metadata, not from the question.

ANSWER   On-Time Delivery % is 87.3% -- 48 of 55 eligible orders delivered on or
         before the promised date

  metric        on_time_delivery_pct
  arithmetic    48 / 55 = 87.2727%
  grain         order (one row per order)
  window        July 2026 (2026-07-01 to 2026-07-31) on promised_delivery_date
  filters       region = IN
  exclusions    cancelled_orders, not_yet_due
  lineage       SAP SD -> SAP EWM -> SAP TM -> fact_order_delivery
  trust         TRUSTED
  gates         7/7 passed: dimensions_declared, exclusions_applied, filters_bound, grain_matches, metric_approved, no_fanout, time_window_bounded
```

The provenance block is not decoration. Every line of it is the answer to a question
somebody will ask in the meeting: which metric, what arithmetic, at what grain, over what
window, with which exclusions, from which systems, and which checks passed.

### The same data, counted wrong

```
2. THE SAME DATA, COUNTED AT DELIVERY GRAIN
==============================================================================


This is the query a text-to-SQL system writes. It is syntactically valid, semantically
reasonable, and joins orders to legs without collapsing to one row per order:

    54 / 61 = 88.5246%   <-- reported as 88.5%

6 orders in this window shipped in more than one leg, so 6 orders voted twice.
The gap is 1.25 points -- small enough to look like rounding, and it errs UPWARD.
A wrong number that flatters you is the one that survives to the board deck.
```

### That query, refused

```
3. THAT QUERY, REFUSED BY NAME -- BEFORE ANY SQL EXISTS
==============================================================================


REFUSED  on_time_delivery_pct: the intent did not pass validation.

  gates failed  grain_matches
  grain_matches        Metric 'on_time_delivery_pct' is certified at grain
                       'order'; the intent asks for grain 'delivery'.
                       Aggregating at the wrong grain changes the number.

  No number is shown. A value that failed a gate is not a caveated
  answer, it is an unverified one.
```

A refusal names the gate and the reason.

> *"I can't answer that, and here is which rule stopped me"* is a system you can put in
> front of a CFO. One that always produces a number is not.

### Why it dropped — the question BI tools can't take

Descriptive questions only need a glossary, a grain and a metric. The question people
actually ask is diagnostic, and answering it needs per-phase baselines and an attribution
rule declared **once, in metadata**:

```
4. THE QUESTION BI TOOLS CANNOT TAKE
   Why did on-time delivery drop for India warehouses last month?
==============================================================================


ANSWER   On-Time Delivery % is 87.3% -- 48 of 55 eligible orders delivered on or
         before the promised date

  metric        on_time_delivery_pct
  arithmetic    48 / 55 = 87.2727%
  grain         order (one row per order)
  window        July 2026 (2026-07-01 to 2026-07-31) on promised_delivery_date
  filters       region = IN
  exclusions    cancelled_orders, not_yet_due
  lineage       SAP SD -> SAP EWM -> SAP TM -> fact_order_delivery
  trust         TRUSTED
  gates         7/7 passed: dimensions_declared, exclusions_applied, filters_bound, grain_matches, metric_approved, no_fanout, time_window_bounded

  BREAKDOWN
    Quality inspection           4
    Transportation               2
    Production execution         1
    unattributed                 0

  Largest contributor: Quality inspection (4 of 7 late orders).

  Transportation ran UNDER its standard on 5 of 7 late orders.
  Logistics was the obvious suspect and logistics was faster than
  planned. Without per-phase baselines you get a plausible, confident,
  wrong story -- and you go optimize the wrong department.

  COMPARISON
    prior window               June 2026 (2026-06-01 to 2026-06-30) on promised_delivery_date
    prior value                96.2% (25 / 26)
    change                     down 8.9pp (96.2% -> 87.3%)
```

That last paragraph is the reason to build any of this. Transportation was the obvious
suspect, and transportation ran *under* its planned standard on five of the seven late
orders. Without per-phase baselines you get a plausible, confident, wrong story — and you
go and optimize the wrong department.

Note `unattributed 0` is printed even though it is zero. An attribution that silently drops
the orders it could not explain is an attribution nobody can audit.

### Four more classes of wrong question

```
5. FOUR MORE CLASSES OF WRONG QUESTION, EACH REFUSED
==============================================================================


-- a filter value outside the declared allowed set
   REFUSED by filters_bound

-- a metric that exists but was never approved
   REFUSED by metric_approved

-- an inverted time window
   REFUSED by time_window_bounded

-- a dimension reachable only through a one-to-many join
   REFUSED by no_fanout
```

`filters_bound` is the quiet one. Without a declared allowed-value set, a filter on a
misspelled region returns zero rows — and zero rows gets presented as an answer.

---

## What this file honestly does not do

Governance code invites overreading, so:

- **One metric, one fact table, one grain.** The full project has three approved metrics,
  nine separate metadata artifacts with different owners, a process model over twelve
  manufacturing phases, and 401 tests.
- **The per-phase variances are embedded, not derived.** In the full project they come from
  SAP timestamps in staging SQL. Here they are a table literal — but the attribution *rule*
  (argmax over declared spans, ties to the earliest phase) is real code, and the file
  refuses to print a breakdown if the embedded rows ever stop matching the orders it
  derives as late.
- **The live resolver path is not exercised here.** It needs credentials; the offline
  resolver stands in. That is a stated gap, not a passing test.
- **This is discovery metadata, not policy enforcement.** An `owner` field records who is
  accountable. It does not stop anyone from querying anything. Access control, consent and
  retention are separate systems, and a semantic layer that implies otherwise is worse than
  one that stays silent.

---

## The complete file

The whole file is 1056 lines, so it ships beside this document rather than inside it:

- **`medium-code.pdf`** — the same file, printed, for reading.
- **`standalone/semantic_layer_demo.py`** — the file itself, sha256 `271b0e57c611`. This is the copy to publish as a Gist; no PDF is a
  reliable place to copy code from.

Nothing else is needed to run it — no repository, no data files, no credentials:

```bash
pip install duckdb pyyaml
python semantic_layer_demo.py
```

---

## The one-line version

Natural-language querying does not fail because models can't write SQL. It fails because
the metadata that makes a question answerable *correctly* — grain, cardinality, exclusions,
approved definitions, process baselines — was never written down where anything could read
it.

Build that, and the model's job shrinks to something it is genuinely good at: choosing.

---

## Where the rest of it lives

This is the third of three pieces on the same build:

- **The short version** — a LinkedIn post on the two numbers, and why the flattering one is
  the one that survives review.
- **The implementation guide** — the long-form LinkedIn article: eight build phases, nine
  metadata artifacts, and the specific natural-language failure each one closes.
- **This post** — the whole architecture as one runnable file.

The full project adds the other two approved metrics, the nine artifacts as separate
governed files with their own owners, data-quality rules that downgrade a trust badge, a
twelve-phase process model, and the test suite that holds every figure above in place. The
single file here is the part you can read in one sitting and run in one command.

**So: what is your team's answer to "which of these two numbers is right"? If it is "ask
Priya," you have a semantic layer — it just isn't written down.**

Leave the answer in a response. The interesting replies are the ones where the honest
answer turns out to be a person.

<div style="page-break-before: always;"></div>

# Part 2 — Publishing checklist

Working notes, deliberately **not** part of `medium-post.md`. Publishing instructions
inside the published article are the clearest sign nobody read it as a reader.

---

## Title and subtitle

Shipped as:

- **Title:** `87.3% or 88.5%? Your LLM Can't Tell — and It Will Pick the Flattering One`
- **Subtitle:** `A governed semantic layer that refuses the wrong number — complete,
  executable Python, two dependencies, no API key.`

Medium treats the first H1 as the title and the following H2 as the subtitle when you
import from a file (`medium.com/p/import`) or paste. Check both landed in the right slots
before publishing — pasted markdown sometimes arrives as two H1s, and a subtitle demoted
to body text loses the search snippet.

Two swaps if the first framing underperforms:

| Alternative title | Trade |
|---|---|
| `Your LLM Writes Valid SQL and Still Returns the Wrong Number` | Broader hook, no numbers — better on social, weaker in search |
| `The Metadata Field That Decides Whether an LLM's Answer Is Right` | Best for search on "metadata"; slower to the point |
| `Why Did On-Time Delivery Drop? Text-to-SQL Can't Say, and That's a Metadata Bug` | Leads with the diagnostic section — the part no BI tool can do — instead of the two numbers. Strongest if the first framing underperforms; costs the numeric hook |
| `87.3% or 88.5%? Text-to-SQL Can't Tell, and That's a Metadata Bug` | The previous shipped title. Best search coverage of the four — `text-to-SQL` and `metadata` both in the title — and the flattest read in a feed. Swap back if search traffic matters more than the click-through |

The shipped title carries `LLM` and the subtitle carries `semantic layer`. `Text-to-SQL`
and `natural-language querying` are left to the tags, the TL;DR and the body, which is a
deliberate trade: the title's job is the click, the tags carry the search.

The title went through one revision. It used to end `...Text-to-SQL Can't Tell, and That's a
Metadata Bug` — accurate, and it read like an internal memo. `and It Will Pick the
Flattering One` is the same claim with the consequence attached, and the consequence is the
part people quote. The subtitle did not change with it — it states what the reader
gets, which is the job the title no longer does. The em-dash clause is also the post's
actual argument: the error is not
random, it errs upward, and that is why it survives review. Keep the numbers at the front —
they are what makes the headline specific rather than another "your AI is lying to you"
post.

## Tags

Five, first one weighted most heavily: **Data Engineering**, **Analytics**, **LLM**,
**Data Governance**, **SQL**.

## Images

| Where | File | Note |
|---|---|---|
| Header | `docs/diagrams/grain_two_ways.png` (2600×1677) | The lead image, and the one that has to survive the feed: it states the whole problem without assuming any vocabulary. Upload the PNG; Medium's SVG support is unreliable. |
| "The rule everything else follows from" | `docs/diagrams/nl_dataflow.png` (2730×1872) | The six stages. Was the lead image and lost that slot deliberately — a pipeline diagram means nothing until the reader accepts the premise. |
| "The metadata: the fields no crawler emits" | `docs/diagrams/metadata_sources.png` (2730×1872) | The figure that answers "can't we just harvest it from SAP?" |

All three are generated — `render_grain.py`, `render_dataflow.py`, `render_sources.py` — so
re-render before uploading if the code has moved. Each takes `--check` and exits non-zero
when the committed figure is stale.

Caption all three — Medium's curators look for it, and an uncaptioned diagram in a
technical post reads as decoration.

## The complete file

The post carries the whole 1,000-plus-line file in one fence, on purpose: the promise is
that a reader can copy it out of the post and run it. That fence is byte-identical to
`standalone/semantic_layer_demo.py`, which `tests/test_standalone.py` executes.

If it reads as too much to scroll, the idiomatic Medium move is a **Gist**: paste the Gist
URL on its own line and Medium expands it inline. Do it as an *addition* — put the Gist
above the fence rather than replacing it — because a Gist is a dead end for anyone reading
on a train with no signal.

Do not hand-edit the fence, or the post and the tested file stop being the same program.
Regenerate instead:

```bash
python content/build_medium_post.py          # rewrites content/medium-post.md
python content/build_medium_post.py --check  # exits 1 if the post on disk is stale
```

## Canonical URL

The LinkedIn article and this post make the same argument. Pick one canonical and set the
other to point at it in Medium's story settings, or the two compete in search and both
rank lower.

## Sequencing with parts 1 and 2

1. `linkedin-post.md` — the short post, first.
2. `linkedin-article.md` — a day or two later, linked from the first post's comments.
3. `medium-post.md` — last, linked from the article's closing section.

Reversed, the short post has nothing left to promise. Do not ship all three the same day;
they compete for the same readers and the article needs the runway.

Replace the three prose references in *"Where the rest of it lives"* with real links once
parts 1 and 2 are live — they are deliberately written as descriptions, not URLs, so the
file has no dead placeholder in it.

## The two audiences

The post opens plain-English — a courier story, three orders counted by hand, and a
five-word glossary — before any YAML appears. That is deliberate. The argument does not
need SQL to land, and a reader who bounces at the first code fence never reaches the part
that would have convinced them.

Do not cut that section to shorten the post, and do not move it below the TL;DR. The
technical reader is handled by its first line, which tells them to skip it.

## If it has to be cut for length

Cut *"The intent"* and *"The compiler"* and keep *"Why it dropped"*. Descriptive querying
is a demo; diagnostic querying is the argument. The diagnostic section is also the only
part of the post that no BI tool can do, which is what makes it the section worth reading.

**Do not cut *"What this file honestly does not do"***, even though it is the easiest
19 lines to lose. A post arguing that overclaiming is the root problem cannot itself
overclaim, and the section is what earns the rest of it the benefit of the doubt. The
same goes for the full provenance block under *"The governed answer"* — it is long, and
being long is the point: every line of it is a question somebody asks in the meeting.

## Pre-flight

- [ ] `python content/build_medium_post.py --check` says the post is current
- [ ] `python -m pytest tests/test_content.py tests/test_standalone.py -q` green
- [ ] the code fence pastes into a clean file and runs on `pip install duckdb pyyaml`
- [ ] all three figures uploaded, captioned, and right-side-up at Medium's width
- [ ] the lead image is `grain_two_ways.png` — that is what the feed shows
- [ ] title in the title slot, subtitle in the subtitle slot
- [ ] five tags, canonical URL decided
- [ ] first response ready: the repo link (Medium does not penalise outbound links the way
      LinkedIn does, so the repo link can also sit in the body)
