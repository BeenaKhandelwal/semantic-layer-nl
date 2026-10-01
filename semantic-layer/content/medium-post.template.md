# 87.3% or 88.5%? Your LLM Can't Tell — and It Will Pick the Flattering One

## A governed semantic layer that refuses the wrong number — complete, executable Python, two dependencies, no API key.

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
{{SNIP:DL-1009A,SO-1009,1,2026-07-16||DL-1018B,SO-1018,2,2026-07-23}}
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
{{SNIP:  - name: on_time_delivery_pct||    lineage: [SAP SD, SAP EWM, SAP TM, fact_order_delivery]}}
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
{{SNIP:entities:||    primary_key: delivery_id}}
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
{{FUNC:build_warehouse}}
```

`max(delivery_date)` is what *"an order counts as delivered only when its final leg
arrives"* means in SQL. Taking `min()` — or joining without aggregating at all — is the
88.5% bug, and it is a one-word difference in a query nobody would flag in review.

---

## The intent: the only thing the model is allowed to produce

```python
{{FUNC:QueryIntent}}
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
{{FUNC:resolve_with_claude}}
```

Two things make this safe, and neither of them is prompt wording.

**The menu is filtered before the model sees it.** `approved` excludes the draft metric, so
the tool's `enum` cannot contain it. An unapproved metric is unaskable because it was never
offered — not because a gate would have caught it afterwards.

**Whatever comes back is still validated.** The system prompt matters less than the fact
that a wrong intent gets refused rather than answered:

```
{{SNIP:You select a governed metric.||An approximation that looks like an answer is worse than a refusal.}}
```

---

## The validator: seven gates, and they fail closed

```python
{{SNIP:GATE_NAMES = ("metric_approved"||    return r}}
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
{{FUNC:answer}}
```

---

## The compiler: the only thing that writes SQL

```python
{{FUNC:compile_sql}}
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
{{OUTPUT:1}}
```

The provenance block is not decoration. Every line of it is the answer to a question
somebody will ask in the meeting: which metric, what arithmetic, at what grain, over what
window, with which exclusions, from which systems, and which checks passed.

### The same data, counted wrong

```
{{OUTPUT:2}}
```

### That query, refused

```
{{OUTPUT:3}}
```

A refusal names the gate and the reason.

> *"I can't answer that, and here is which rule stopped me"* is a system you can put in
> front of a CFO. One that always produces a number is not.

### Why it dropped — the question BI tools can't take

Descriptive questions only need a glossary, a grain and a metric. The question people
actually ask is diagnostic, and answering it needs per-phase baselines and an attribution
rule declared **once, in metadata**:

```
{{OUTPUT:4}}
```

That last paragraph is the reason to build any of this. Transportation was the obvious
suspect, and transportation ran *under* its planned standard on five of the seven late
orders. Without per-phase baselines you get a plausible, confident, wrong story — and you
go and optimize the wrong department.

Note `unattributed 0` is printed even though it is zero. An attribution that silently drops
the orders it could not explain is an attribution nobody can audit.

### Four more classes of wrong question

```
{{OUTPUT:5}}
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

Copy this into `semantic_layer_demo.py` and run it. Nothing else is needed — no repository,
no data files, no credentials.

```python
{{CODE}}
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
