# semantic-layer-nl

A worked, fully-tested implementation of a **semantic layer for trustworthy
natural-language analytics** — how to let people (and LLMs) ask questions of SAP-style
data in plain English and get a *governed, defensible* number instead of a plausible wrong
one.

The project lives in **[`semantic-layer/`](semantic-layer/)**. Start with its
[README](semantic-layer/README.md).

- **The problem, in one line:** the same question — *"on-time delivery for India warehouses
  last month"* — can produce **88.5%** or **87.3%** from the same warehouse on the same day.
  One is wrong, and nothing in the SQL tells you which.
- **The fix:** the model never writes SQL and never does arithmetic. It picks a governed
  metric and emits validated JSON; a deterministic compiler produces the SQL, and seven
  validation gates run *before* any SQL exists.
- **Reproduce it:** no API key, no network — see
  [`semantic-layer/README.md`](semantic-layer/README.md).

Write-ups are in [`semantic-layer/content/`](semantic-layer/content/): a LinkedIn post, a
long-form article, and a Medium post carrying the complete runnable file.
