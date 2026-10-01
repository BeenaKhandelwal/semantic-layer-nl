"""Run a CompiledQuery against DuckDB. Read-only, no LLM, no query construction.

Deliberately the thinnest module in the pipeline. It does not build SQL, does not modify
it, and cannot: it takes the compiler's text and params and hands them to DuckDB
unchanged. Keeping it thin is the point -- if this module could rewrite a query, the
compiler would stop being the single place the arithmetic is decided.

The connection is opened read-only so no pipeline path can mutate the warehouse. An
answer-serving system has no business writing to the mart it reads.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb

from src.semantic.compiler import CompiledQuery
from src.semantic.constants import DB_PATH


def run(cq: CompiledQuery, db_path: Path | str | None = None) -> list[dict[str, Any]]:
    """Execute the compiled query and return rows as dicts keyed by column name.

    Dicts rather than tuples because provenance and the CLI both address columns by name
    (`row["denominator"]`), and positional access would silently shift the moment a
    dimension is added to the SELECT list.
    """
    path = Path(db_path) if db_path is not None else DB_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"No warehouse at {path}. Build it first: python -m src.build_warehouse"
        )
    con = duckdb.connect(str(path), read_only=True)
    try:
        cursor = con.execute(cq.sql, cq.params)
        columns = [d[0] for d in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        con.close()
