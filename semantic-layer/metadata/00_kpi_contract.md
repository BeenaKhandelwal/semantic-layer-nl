# Phase 0: KPI Contract — Agreed Metric Definitions

**Purpose:** This contract defines the metrics this semantic layer must answer, the business decisions they support, who owns each metric, and the acceptance criteria for "done". Without an agreed definition, two people asking the same question get two different numbers, and neither is wrong.

**Owner:** Chief Supply Chain Officer  
**Steward:** Supply Chain Analytics Council  
**Last Reviewed:** 2026-08-01  
**Status:** Approved

---

## The Two Demonstrator Questions

These are the verbatim natural-language questions the MVP must answer, drawn from real executive reporting requirements. Both answers are computed from committed sample data (Section 5 of design.md) and asserted in the acceptance criteria, so every published figure is reproducible rather than illustrative.

### Question 1 (Descriptive): What was on-time delivery performance for India warehouses last month?

**Resolves to:** `on_time_delivery_pct` metric, filtered to `region = 'IN'`, time window July 2026.

**Expected Answer:**
> **87.3%** (48 of 55 eligible orders delivered on time).

**Business Context:** Monthly executive scorecard. This number gates the quarterly bonus for the India supply chain team. If OTD falls below 85%, a corrective action plan is triggered.

---

### Question 2 (Diagnostic): Why did on-time delivery drop for India warehouses last month?

**Resolves to:** Same metric and filters as Q1, broken out by `delay_attribution_phase` dimension, with a comparison against the prior month (June 2026).

**Expected Answer:**
> **87.3%, down 8.9pp from 96.2% in June** (25 of 26 eligible). 7 orders were late. Attribution: **quality inspection 4**, transportation 2, production execution 1. On those 4 orders, QM usage decision ran an average 4.75 days over its 1.0-day standard, against 0 days of available slack — the promise left no room to absorb it. Plant 1010.

**Business Context:** Root-cause analysis for performance drops. This attribution drives targeted process improvements: if QM is the bottleneck, invest in faster inspection equipment or additional QM staff; if transportation dominates, renegotiate carrier SLAs or add backup carriers.

---

## The Four Governed Metrics

| Metric | Definition | Grain | Owner | Steward | Business Decision Supported |
|--------|------------|-------|-------|---------|---------------------------|
| **On-Time Delivery %** | Share of eligible customer orders delivered on or before the promised delivery date | `order` | VP Supply Chain | Supply Chain Analytics Lead | Executive scorecard; supplier performance reviews; quarterly bonus gates |
| **Manufacturing Schedule Adherence %** | Share of production orders confirmed on or before the scheduled finish date | `production_order` | VP Manufacturing | Production Planning Lead | Manufacturing capacity planning; shift scheduling; bottleneck identification |
| **First Pass Yield %** | Share of production orders accepted at the **first** quality inspection decision | `production_order` | VP Quality | Quality Analytics Lead | Quality investment prioritization; defect root-cause analysis; supplier quality management |
| **Production Cycle Time (days)** _(deferred, not in MVP)_ | Average days from production order release to goods receipt | `production_order` | VP Manufacturing | Industrial Engineering | Lean initiatives; process improvement projects; lead time quoting |

The first three are governed and queryable. **Production Cycle Time is contracted but not
implemented** (design §10.2): it is a plain average over columns the other three already
materialize, so it teaches nothing new for the cost of building it. It is listed here
because the contract is the place to record an agreed definition *before* implementation —
but asking for it will be refused by the validator rather than answered, which is the
correct behaviour for a metric that has no approved implementation.

### What "last month" resolves to

Both questions above say "last month", and that phrase alone is not answerable. The
governed reading is **`promised_delivery_date` within the month** — the promise is what
the customer was told and what the metric is judged against. This matters concretely:

| Reading of "last month" | IN, July 2026 | |
|---|---|---|
| `promised_delivery_date` in July (**governed**) | 48/55 = **87.27%** | the answer |
| `order_date` in July | 33/40 = 82.50% | a different question: orders *placed* in July, some still open |
| `final_delivery_date` in July | 48/55 = 87.27% | coincides here, but drifts whenever a late order lands in the next month |

An ungrounded resolver picking `order_date` returns 82.5% — plausible, precise, and
wrong by 4.8pp. Nothing in the number itself reveals the substitution, which is why the
date semantics are contracted here rather than left to inference.

---

## Why These Metrics Matter

### The Grain Problem (Phase 2)

**Without a declared grain, the split-delivery fan-out inflates OTD from 87.3% to 88.5%.**

- 6 orders ship in two legs (deliveries_raw.csv has 2 rows per order_id for SO-1009, SO-1012, SO-1014, SO-1016, SO-1017, SO-1018).
- Joining at delivery grain (one row per delivery leg) double-counts split shipments in the numerator.
- The wrong number (88.5%) is both **close enough to look plausible** and **flattering** — a performance overstatement survives review because it makes the team look good.
- The semantic model declares `grain: order` and the validator rejects delivery-grain queries.

### The Rework Trap (Phase 3)

**Without an exclusion rule, First Pass Yield reads 94.5% instead of 94.4%.**

- SO-1004 has a rework loop: inspection lot QL-4004 has two usage decisions (decision_seq 1 = REWORK, decision_seq 2 = ACCEPT).
- Counting all decisions treats the reworked lot as both a failure and a success, understating the defect rate.
- The metric definition in `05_semantic_model.yml` specifies: *"first usage decision only (decision_seq = 1); excludes rework re-inspections"*.
- The compiler applies this exclusion unconditionally, so every query gets the same answer.

### The Attribution Rule (Phase 4)

**Without per-phase baselines and a variance rule, "why did OTD drop" is unanswerable.**

- Each phase has a standard duration (e.g. quality inspection = 1 day, production execution = 3 days).
- For each order, `variance_days = actual_duration - standard_duration` per phase.
- `delay_attribution_phase = argmax(variance_days)` over the **9 variance spans** (phase_seq 2–10),
  evaluated only for late delivered eligible orders. Phase 1 is the chain's start point rather than a
  span, phase 11 is a 0-day event folded into `var_shipment`, and phase 12 follows delivery — so those
  three phases are not emittable attribution values.
- This rule is defined once in `04_process_model.yml` and implemented in `sql/02_staging_model.sql` as a derived column. The LLM never computes it.

---

## Exclusions (What Counts as Eligible)

| Metric | Exclusions | Rationale |
|--------|------------|-----------|
| On-Time Delivery % | Cancelled orders (`order_status = 'CANC'`) | A cancelled order was never due; including it inflates the denominator |
| | Not-yet-due orders (`promised_delivery_date > AS_OF_DATE`) | An order promised after the as-of date is not late, it is pending |
| Manufacturing Schedule Adherence % | Cancelled production orders | Same rationale as OTD |
| First Pass Yield % | Rework re-inspections (`decision_seq > 1`) | Prevents double-counting; measures right-first-time |
| Production Cycle Time | Cancelled production orders | Incomplete orders distort the average |

**Critical:** These exclusions are not suggestions. They are implemented as predicates in `05_semantic_model.yml` and applied unconditionally by the compiler. A validator gate (`exclusions_applied`) ensures they are present before SQL is generated.

---

## Test Oracle and Acceptance Criteria

**Committed data:** `data/seed_core.csv` (20 hand-authored orders) + `data/generate.py` (112 generated) → 132 total orders.

**Canonical numbers** (from `design.md` §5.1, verified by `tests/test_compiler.py`):

| Quantity | Value | Test |
|----------|-------|------|
| OTD, IN July 2026 | 48/55 = 87.2727% | `test_q1_otd_india_july_is_87_27_percent` |
| OTD, IN June 2026 | 25/26 = 96.1538% | `test_otd_india_june_is_96_15_percent` |
| Drop | 8.88pp | `test_the_drop_is_8_88_pp` |
| Late attribution, IN July | quality_inspection 4, transportation 2, production_execution 1 | `test_q2_attribution_breakdown` |
| Naive delivery-grain OTD (wrong) | 54/61 = 88.5246% | `test_naive_delivery_grain_overstates_to_88_52` |
| First-pass yield, IN July | 51/54 = 94.4444% | `test_fpy_correct_and_naive` |
| Naive FPY counting rework (wrong) | 52/55 = 94.5455% | same test |
| Schedule adherence, IN July | 50/54 = 92.5926% | `test_schedule_adherence` |

**Definition of done:**

1. `python src/ask.py --offline Q1` returns 87.3% with lineage, exclusions applied, and trust badge = TRUSTED.
2. `python src/ask.py --offline Q2` returns the attribution breakdown with quality_inspection = 4.
3. `python -m pytest` → 34+ tests pass, including all canonical number assertions.
4. No `ANTHROPIC_API_KEY` required for offline operation (golden intents bypass the resolver).
5. The demo's `AS_OF_DATE` appears as a literal in exactly one place, `src/semantic/constants.py`;
   no metadata artifact restates it. (Grepping for the date here would put the literal in this
   file and break the rule it describes.)

---

## Related Artifacts

- **Phase 1 (Technical Metadata):** `01_technical_metadata.json` — SAP DDIC field mappings, shows *where* the data lives
- **Phase 2 (Standardized Metadata):** `02_standardized_metadata.json` — grain declarations, prevents the 88.5% error
- **Phase 3 (Glossary + Bindings):** `03_glossary.yml`, `03_column_bindings.yml` — maps business terms to columns
- **Phase 4 (Process Model):** `04_process_model.yml` — the 12 phases and variance rule, makes "why" computable
- **Phase 5 (Semantic Model):** `05_semantic_model.yml` — executable metric definitions with exclusions
- **Phase 6 (Data Quality):** `06_dq_rules.yml` — 6 dimension rules with trust badge, gates low-quality results
- **Phase 7 (Catalog):** `07_catalog_asset.json` — governance metadata for compliance and discovery

---

## Sign-Off

By approving this contract, the executive team agrees that:

1. These four metrics, as defined here, are the official versions for reporting and decision-making.
2. Any other calculation — even if numerically close — is unofficial and must not be used for performance evaluation or bonus determination.
3. Changes to metric definitions require approval from the Supply Chain Analytics Council and must be versioned in this document.
4. The semantic layer is the single source of truth for these metrics. Dashboard queries, ad-hoc analyses, and LLM-generated answers must all resolve through the governed semantic model.

**Approved by:**

- Chief Supply Chain Officer: _________________ Date: _______
- VP Supply Chain: _________________ Date: _______
- VP Manufacturing: _________________ Date: _______
- VP Quality: _________________ Date: _______
- Chief Data Officer: _________________ Date: _______

**Next Review:** 2026-11-01 (quarterly)
