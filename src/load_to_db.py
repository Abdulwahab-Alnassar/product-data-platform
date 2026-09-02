import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

CLEANED_DATA_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "cleaned_products.csv"
)

DATABASE_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "products.db"
)

SCHEMA_PATH = PROJECT_ROOT / "sql" / "schema.sql"


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
        raise FileNotFoundError(
            f"Cleaned dataset not found: {file_path}"
        )

    return pd.read_csv(file_path)


def validate_columns(data: pd.DataFrame) -> None:
    """Ensure that all required database columns exist."""

    missing_columns = [
        column
        for column in DATABASE_COLUMNS
        if column not in data.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Missing columns: {missing_columns}"
        )


def prepare_data(data: pd.DataFrame) -> pd.DataFrame:
    """Prepare rows before inserting them into SQLite."""

    prepared_data = data.copy()

    duplicate_products = prepared_data[
        "product_id"
    ].duplicated().sum()

    if duplicate_products:
        prepared_data = (
            prepared_data
            .sort_values(
                by="rating_count",
                ascending=False,
                na_position="last",
            )
            .drop_duplicates(
                subset=["product_id"],
                keep="first",
            )
        )

    prepared_data = prepared_data[DATABASE_COLUMNS]

    print(
        "Duplicate product IDs removed: "
        f"{duplicate_products}"
    )

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
) -> int:
    """Create the database and insert product records."""

    DATABASE_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    schema = SCHEMA_PATH.read_text(
        encoding="utf-8"
    )

    placeholders = ", ".join(
        ["?"] * len(DATABASE_COLUMNS)
    )

    column_names = ", ".join(DATABASE_COLUMNS)

    insert_query = f"""
        INSERT INTO products ({column_names})
        VALUES ({placeholders})
    """

    records = create_records(data)

    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.executescript(schema)

        # Make the script repeatable without duplicating data.
        connection.execute("DELETE FROM products")

        connection.executemany(
            insert_query,
            records,
        )

        database_count = connection.execute(
            "SELECT COUNT(*) FROM products"
        ).fetchone()[0]

    return database_count


def main() -> None:
    data = load_cleaned_data(CLEANED_DATA_PATH)

    validate_columns(data)

    prepared_data = prepare_data(data)

    database_count = load_database(prepared_data)

    print(f"CSV rows prepared: {len(prepared_data)}")
    print(f"Database rows:      {database_count}")
    print(f"Database saved to:  {DATABASE_PATH}")

    if len(prepared_data) != database_count:
        raise ValueError(
            "CSV and database row counts do not match."
        )

    print("Database validation passed.")


if __name__ == "__main__":
    main()