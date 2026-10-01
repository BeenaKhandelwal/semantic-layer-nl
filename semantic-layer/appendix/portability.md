# Appendix: Portability

`metadata/05_semantic_model.yml` is deliberately tool-neutral. Nothing in it is DuckDB-
specific and nothing depends on this project's Python. This appendix maps each concept
onto the platforms you are most likely to be moving to.

The more useful column is the last one. Where a platform has **no** equivalent, that gap
is a governance decision you inherit: the concept still exists in your data, it just has
nowhere to live in metadata, so it survives only as convention.

## Concept mapping

| This project | dbt MetricFlow | Cube | Databricks Unity Catalog | SAP Datasphere |
|---|---|---|---|---|
| `entities:` | `semantic_model` with `entities` | `cube` | table / view + `PRIMARY KEY` constraint | Analytic / Fact model |
| `entity.grain` | implied by the primary `entity` | implied by the cube's `sql` | **no first-class field** — convention or a table comment | Fact model granularity |
| `entity.primary_key` | `entity: {type: primary}` | `primary_key: true` on a dimension | `PRIMARY KEY` (informational, not enforced) | Key attribute |
| `dimensions:` | `dimensions:` | `dimensions:` | column + `COMMENT`; tags for grouping | Attribute / Dimension |
| `dimension.allowed_values` | **no field** — enforce in tests | **no field** — enforce upstream | `CHECK` constraint (enforced) | Value help / domain |
| `metrics:` | `metrics:` | `measures:` | Metric view (`CREATE VIEW ... WITH METRICS`) | Calculated measure |
| `metric.expression` (ratio) | `type: ratio` with `numerator`/`denominator` | `measures` + a calculated measure | SQL in the metric view | Calculated measure formula |
| `metric.grain` | `agg_time_dimension` + entity grain | cube grain | metric view's `FROM` grain | Measure granularity |
| `metric.time_dimension` | `agg_time_dimension` | `timeDimension` | metric view time column | Time dimension binding |
| `metric.exclusions` | `filter:` on the metric | `filters:` on the measure | `WHERE` in the metric view | Filter in the calculated measure |
| `joins[].cardinality` | inferred from `entity` types (`primary`/`foreign`) | `relationship: one_to_many` etc. | `FOREIGN KEY` (informational) | Association cardinality |
| `metric.approval_state` | **no field** — Explorer exposure or a tag | **no field** — access policy | Certified tag / `CERTIFIED` in Catalog | Released / consumable status |
| `metric.owner` / `steward` | `meta:` | `meta:` | Owner (first-class) + tags | Responsible / owner |
| `metric.lineage` | derived from the DAG | derived from `sql` | derived (System Tables lineage) | Derived (Impact & Lineage) |
| `06_dq_rules.yml` | dbt tests / `dbt-expectations` | **no equivalent** — upstream | Delta expectations, Lakehouse Monitoring | Data quality (SAP Datasphere DQ) |
| `07_catalog_asset.json` | **no equivalent** — external catalog | **no equivalent** | Catalog metadata, tags, certification | Catalog / Marketplace entry |

Two additional catalog platforms, which sit beside a semantic layer rather than
replacing it:

| This project | Atlan | Collibra |
|---|---|---|
| `03_glossary.yml` terms + synonyms | Glossary term with synonyms | Business term with synonyms and relations |
| `03_column_bindings.yml` | Term ↔ column linkage | Term ↔ data element relation |
| `metric.owner` / `steward` | Owner / expert | Responsibility (steward role) |
| `metric.approval_state` | Certification status | Approval workflow status |
| `07_catalog_asset.json` governance fields | Custom metadata attributes | Custom attributes / data-privacy domain |
| Metric definitions | Linked, not defined | Linked, not defined |

## The three gaps worth planning for

**Grain is rarely a first-class field.** MetricFlow and Cube derive it from the model's
shape; Unity Catalog has no field for it at all. Since a wrong grain is what produces
this project's 88.52% wrong answer, the check has to live somewhere — a test, a
constraint, or a contract — and moving platforms does not move that obligation.

**Allowed values usually enforce upstream or not at all.** Only Unity Catalog's `CHECK`
constraints actually enforce. Elsewhere, `allowed_values` is documentation, and the
validator (or a dbt test) is what turns it into a rule. Without one, a filter on a
misspelled region returns zero rows and presents that as an answer.

**Approval state is a tag almost everywhere.** Which means "approved" is only as strong
as the process that applies the tag and the code that reads it. In this project the
retriever filters on it, so an unapproved metric is never offered to the resolver at
all — that read is the part that matters, and it is easy to port and easy to forget.
