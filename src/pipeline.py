"""Run the existing extract, transform, and load stages in one command."""

from pathlib import Path
from typing import Optional

from src import clean_data as cleaning
from src import load_to_db as database


def run_pipeline(
    raw_data_path: Optional[Path] = None,
) -> dict[str, int]:
    """Process a raw CSV and return counts for the completed run."""

    source_path = (
        cleaning.RAW_DATA_PATH
        if raw_data_path is None
        else Path(raw_data_path)
    )

    print(f"[1/5] Extract: reading {source_path}")
    raw_data = cleaning.load_data(source_path)

    if raw_data.empty:
        raise ValueError("The raw dataset contains no rows.")

    print("[2/5] Transform: cleaning product data")
    cleaned_data = cleaning.clean_data(raw_data)

    print("[3/5] Validate: checking columns and preparing unique products")
    database.validate_columns(cleaned_data)

    # The current loader replaces the table contents. Do not clear an
    # existing database when there are no usable input rows.
    if cleaned_data.empty:
        raise ValueError("No usable products remain after cleaning.")

    prepared_data = database.prepare_data(cleaned_data)

    print("[4/5] Save: writing the cleaned CSV and public sample")
    cleaning.save_data(cleaned_data)

    print("[5/5] Load: writing products to SQLite")
    database_count = database.load_database(prepared_data)
    expected_count = len(prepared_data)

    if database_count != expected_count:
        raise ValueError(
            "Database row count mismatch: "
            f"expected {expected_count}, found {database_count}."
        )

    return {
        "raw_rows": len(raw_data),
        "cleaned_rows": len(cleaned_data),
        "removed_rows": len(raw_data) - len(cleaned_data),
        "duplicate_product_ids": len(cleaned_data) - expected_count,
        "database_rows": database_count,
    }


def main() -> None:
    summary = run_pipeline()

    print("\nPipeline completed successfully.")
    print(f"Rows read:                    {summary['raw_rows']}")
    print(f"Rows after cleaning:          {summary['cleaned_rows']}")
    print(f"Rows removed during cleaning: {summary['removed_rows']}")
    print(f"Duplicate product IDs:        {summary['duplicate_product_ids']}")
    print(f"Products in database:         {summary['database_rows']}")
    print("Database validation passed.")
    print(f"Cleaned CSV: {cleaning.PROCESSED_DATA_PATH}")
    print(f"Public sample: {cleaning.SAMPLE_DATA_PATH}")
    print(f"Database: {database.DATABASE_PATH}")


if __name__ == "__main__":
    main()
