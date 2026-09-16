import sqlite3
import logging
from contextlib import closing
from pathlib import Path
from typing import Any, Optional

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

CLEANED_DATA_PATH = PROJECT_ROOT / "data" / "processed" / "cleaned_products.csv"

DATABASE_PATH = PROJECT_ROOT / "data" / "processed" / "products.db"

SCHEMA_PATH = PROJECT_ROOT / "sql" / "schema.sql"
VIEWS_PATH = PROJECT_ROOT / "sql" / "views.sql"
LOGGER = logging.getLogger("product_data_platform")


DATABASE_COLUMNS = [
    "product_id",
    "product_name",
    "category",
    "discounted_price",
    "actual_price",
    "discount_percentage",
    "rating",
    "rating_count",
    "about_product",
    "review_id",
    "review_title",
    "review_content",
    "img_link",
    "product_link",
]


def load_cleaned_data(file_path: Path) -> pd.DataFrame:
    """Load the cleaned product data."""

    if not file_path.exists():
        raise FileNotFoundError(f"Cleaned dataset not found: {file_path}")

    return pd.read_csv(file_path)


def validate_columns(data: pd.DataFrame) -> None:
    """Ensure that all required database columns exist."""

    missing_columns = [
        column for column in DATABASE_COLUMNS if column not in data.columns
    ]

    if missing_columns:
        raise ValueError(f"Missing columns: {missing_columns}")


def prepare_data(data: pd.DataFrame) -> pd.DataFrame:
    """Prepare rows before inserting them into SQLite."""

    prepared_data = data.copy()

    duplicate_products = prepared_data["product_id"].duplicated().sum()

    if duplicate_products:
        prepared_data = prepared_data.sort_values(
            by="rating_count",
            ascending=False,
            na_position="last",
            kind="stable",
        ).drop_duplicates(
            subset=["product_id"],
            keep="first",
        )

    prepared_data = prepared_data[DATABASE_COLUMNS]

    LOGGER.info("Duplicate product IDs removed: %s", duplicate_products)

    return prepared_data


def convert_value(value: Any) -> Any:
    """Convert pandas values into SQLite-compatible values."""

    if pd.isna(value):
        return None

    if hasattr(value, "item"):
        return value.item()

    return value


def create_records(
    data: pd.DataFrame,
) -> list[tuple[Any, ...]]:
    """Convert the DataFrame into database records."""

    return [
        tuple(convert_value(value) for value in row)
        for row in data.itertuples(
            index=False,
            name=None,
        )
    ]


def load_database(
    data: pd.DataFrame,
    database_path: Optional[Path] = None,
) -> int:
    """Upsert a batch atomically; return verified batch rows, not table size.

    Incoming values (including NULL) replace existing values for matching
    IDs. Products absent from this batch remain in the database.
    """
    validate_columns(data)
    data = data[DATABASE_COLUMNS].copy()
    if data.empty:
        raise ValueError("Cannot load an empty batch.")
    for name in ("product_id", "product_name"):
        values = data[name].astype("string").str.strip()
        if (values.isna() | values.eq("")).any():
            raise ValueError(f"Missing or blank {name}.")
        data[name] = values
    if data["product_id"].duplicated().any():
        raise ValueError("Duplicate product IDs in prepared batch.")

    target = DATABASE_PATH if database_path is None else Path(database_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    columns = ", ".join(DATABASE_COLUMNS)
    placeholders = ", ".join("?" for _ in DATABASE_COLUMNS)
    updates = ", ".join(
        f"{column} = excluded.{column}"
        for column in DATABASE_COLUMNS
        if column != "product_id"
    )
    query = (
        f"INSERT INTO products ({columns}) VALUES ({placeholders}) "
        f"ON CONFLICT(product_id) DO UPDATE SET {updates}"
    )
    records = create_records(data)

    with closing(sqlite3.connect(target)) as connection:
        connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        connection.executescript(VIEWS_PATH.read_text(encoding="utf-8"))
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript(
            (PROJECT_ROOT / "sql/changes.sql").read_text(encoding="utf-8")
        )
        with connection:
            # A temporary table lets us verify all incoming values in one
            # query, including NULLs, before committing the batch.
            connection.execute(
                f"CREATE TEMP TABLE batch_products AS "
                f"SELECT {columns} FROM products WHERE 0"
            )
            connection.executemany(
                f"INSERT INTO batch_products ({columns}) VALUES ({placeholders})",
                records,
            )
            connection.executemany(query, records)
            matches = " AND ".join(
                f"p.{column} IS b.{column}" for column in DATABASE_COLUMNS
            )
            verified_count = connection.execute(
                "SELECT COUNT(*) FROM batch_products b "
                "JOIN products p ON p.product_id = b.product_id "
                f"WHERE {matches}"
            ).fetchone()[0]
            if verified_count != len(records):
                raise ValueError("Stored values do not match the incoming batch.")
    return verified_count


def get_database_count(database_path: Optional[Path] = None) -> int:
    target = DATABASE_PATH if database_path is None else Path(database_path)
    with closing(
        sqlite3.connect(target.resolve().as_uri() + "?mode=ro", uri=True)
    ) as connection:
        return connection.execute("SELECT COUNT(*) FROM products").fetchone()[0]


def main() -> None:
    data = load_cleaned_data(CLEANED_DATA_PATH)

    validate_columns(data)

    prepared_data = prepare_data(data)

    database_count = load_database(prepared_data)

    print(f"CSV rows prepared: {len(prepared_data)}")
    print(f"Verified batch rows: {database_count}")
    print(f"Total database rows: {get_database_count()}")
    print(f"Database saved to:  {DATABASE_PATH}")

    if len(prepared_data) != database_count:
        raise ValueError("CSV and database row counts do not match.")

    print("Database validation passed.")


if __name__ == "__main__":
    main()
