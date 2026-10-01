"""Frozen constants. No wall-clock, no randomness anywhere in this project."""
from datetime import date
from pathlib import Path

# The demo's "today". Every relative date ("last month") resolves against this.
# Never call date.today() -- it would make results drift and tests flaky.
AS_OF_DATE = date(2026, 8, 7)

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
METADATA_DIR = REPO_ROOT / "metadata"
SQL_DIR = REPO_ROOT / "sql"
DB_PATH = REPO_ROOT / "warehouse.duckdb"
