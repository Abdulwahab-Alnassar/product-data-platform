from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_PATH = PROJECT_ROOT / "data" / "raw" / "amazon.csv"
SAMPLE_DATA_PATH = PROJECT_ROOT / "data" / "sample" / "amazon_sample.csv"


def load_data(file_path: Path) -> pd.DataFrame:
    """Load product data from a CSV file."""

    if not file_path.exists():
        raise FileNotFoundError(f"Dataset was not found at: {file_path}")

    return pd.read_csv(file_path)


def inspect_data(data: pd.DataFrame) -> None:
    """Display useful information about the dataset."""

    print("\n=== DATASET OVERVIEW ===")
    print(f"Number of rows: {data.shape[0]}")
    print(f"Number of columns: {data.shape[1]}")
    print(f"Duplicate rows: {data.duplicated().sum()}")

    memory_mb = data.memory_usage(deep=True).sum() / (1024**2)
    print(f"Memory usage: {memory_mb:.2f} MB")

    print("\n=== COLUMN NAMES ===")
    for column in data.columns:
        print(f"- {column}")

    print("\n=== DATA TYPES ===")
    print(data.dtypes)

    print("\n=== MISSING VALUES ===")
    missing_values = data.isna().sum()
    missing_values = missing_values[missing_values > 0]

    if missing_values.empty:
        print("No missing values were found.")
    else:
        print(missing_values.sort_values(ascending=False))

    preview_columns = [
        column
        for column in [
            "product_id",
            "product_name",
            "category",
            "discounted_price",
            "rating",
        ]
        if column in data.columns
    ]

    print("\n=== FIRST FIVE PRODUCTS ===")
    print(data[preview_columns].head().to_string(index=False))


def save_safe_sample(data: pd.DataFrame, file_path: Path) -> None:
    """Save a small sample without direct user identifiers."""

    identifying_columns = ["user_id", "user_name"]

    safe_sample = data.drop(
        columns=identifying_columns,
        errors="ignore",
    ).head(100)

    file_path.parent.mkdir(parents=True, exist_ok=True)
    safe_sample.to_csv(file_path, index=False)

    print(f"\nSafe sample saved to: {file_path}")
    print(f"Sample rows: {len(safe_sample)}")


def main() -> None:
    product_data = load_data(RAW_DATA_PATH)
    inspect_data(product_data)
    save_safe_sample(product_data, SAMPLE_DATA_PATH)


if __name__ == "__main__":
    main()
