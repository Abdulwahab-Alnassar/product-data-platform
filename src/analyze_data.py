"""Run the saved advanced SQL queries against an existing database."""

import argparse
import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd

from src.load_to_db import DATABASE_PATH, PROJECT_ROOT

QUERIES_PATH = PROJECT_ROOT / "sql" / "advanced_queries.sql"


def run_analysis(database_path: Path):
    path = Path(database_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Database not found: {path}. Run the pipeline first.")
    # Read-only mode prevents accidentally creating or modifying a database.
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as connection:
        for number, statement in enumerate(
            QUERIES_PATH.read_text(encoding="utf-8").split(";"), 1
        ):
            if not statement.strip():
                continue
            result = pd.read_sql_query(statement, connection)
            print(f"\nQuery {number} ({len(result)} rows)")
            print(result.to_string(index=False))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DATABASE_PATH)
    args = parser.parse_args(argv)
    run_analysis(args.database)


if __name__ == "__main__":
    main()
