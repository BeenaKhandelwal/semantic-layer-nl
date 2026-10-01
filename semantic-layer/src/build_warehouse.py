"""Build the DuckDB warehouse from committed CSVs. Idempotent, offline.

Every table and view is defined in sql/02_staging_model.sql with CREATE OR REPLACE,
so a rebuild refreshes whatever the script declares. It cannot, however, remove an
object the script has stopped declaring: DuckDB persists to a file, so a renamed or
deleted view lingers from an earlier build and later queries keep resolving against
the stale definition. That surfaced during review -- a test passed only because a
view left over from a previous build was still there. `build(fresh=True)` deletes the
file first, which is what the tests use.
"""
import sys
from pathlib import Path

import duckdb

# Run-as-script bootstrap, matching src/ask.py. `python src/build_warehouse.py` -- the
# first command in the README -- puts `src/` on sys.path rather than the repo root, so
# the absolute import below raised ModuleNotFoundError on a clean clone. It worked here
# only because every caller reached this module a different way: the tests via pytest's
# `pythonpath = .`, and verify_acceptance.py by importing it as `src.build_warehouse`.
# So the one documented invocation was the one nothing exercised.
if __package__ in (None, ""):  # pragma: no cover -- depends on invocation form
    _root = str(Path(__file__).resolve().parents[1])
    if _root not in sys.path:
        sys.path.insert(0, _root)

from src.semantic.constants import AS_OF_DATE, DATA_DIR, DB_PATH, SQL_DIR


def build(db_path=None, fresh=False):
    """Build the warehouse at `db_path` (default: constants.DB_PATH).

    fresh=True removes an existing database file first, guaranteeing the result
    contains exactly what the SQL script declares and nothing carried over.
    """
    db_path = Path(db_path) if db_path else DB_PATH
    sql = (SQL_DIR / "02_staging_model.sql").read_text(encoding="utf-8")
    # AS_OF_DATE lives only in constants.py; the SQL carries a token and we bind it
    # here so the demo's "today" can never drift between Python and SQL.
    sql = sql.replace("__DATA_DIR__", DATA_DIR.as_posix())
    sql = sql.replace("__AS_OF_DATE__", AS_OF_DATE.isoformat())
    if fresh:
        db_path.unlink(missing_ok=True)
    con = duckdb.connect(str(db_path))
    try:
        con.execute(sql)
    finally:
        con.close()


if __name__ == "__main__":
    build(fresh=True)
    print(f"Built warehouse at {DB_PATH}")
