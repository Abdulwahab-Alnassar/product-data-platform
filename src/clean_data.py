from pathlib import Path
from typing import Optional

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

RAW_DATA_PATH = PROJECT_ROOT / "data" / "raw" / "amazon.csv"
PROCESSED_DATA_PATH = (
    PROJECT_ROOT / "data" / "processed" / "cleaned_products.csv"
)
SAMPLE_DATA_PATH = (
    PROJECT_ROOT / "data" / "sample" / "cleaned_products_sample.csv"
)


def load_data(file_path: Path) -> pd.DataFrame:
    """Load the raw Amazon dataset."""

    if not file_path.exists():
        raise FileNotFoundError(f"Dataset not found: {file_path}")

    return pd.read_csv(file_path)


def clean_currency(series: pd.Series) -> pd.Series:
    """Convert values such as ₹1,099 into numeric values."""

    cleaned_series = (
        series.astype("string")
        .str.replace("₹", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.strip()
    )

    return pd.to_numeric(cleaned_series, errors="coerce")


def clean_percentage(series: pd.Series) -> pd.Series:
    """Convert values such as 64% into numeric values."""

    cleaned_series = (
        series.astype("string")
        .str.replace("%", "", regex=False)
        .str.strip()
    )

    return pd.to_numeric(cleaned_series, errors="coerce")


def clean_count(series: pd.Series) -> pd.Series:
    """Convert values such as 24,269 into integer values."""

    cleaned_series = (
        series.astype("string")
        .str.replace(",", "", regex=False)
        .str.strip()
    )

    numeric = pd.to_numeric(cleaned_series, errors="coerce")
    # Fractional/infinite counts are invalid, not values to round silently.
    numeric = numeric.where(numeric.mod(1).eq(0).fillna(False))
    return numeric.astype("Int64")


def clean_data(data: pd.DataFrame) -> pd.DataFrame:
    """Clean and validate the Amazon product dataset."""

    cleaned_data = data.copy()

    # Standardize column names.
    cleaned_data.columns = (
        cleaned_data.columns
        .str.strip()
        .str.lower()
    )

    # Remove extra spaces from text columns.
    text_columns = cleaned_data.select_dtypes(
        include=["object", "string"]
    ).columns

    for column in text_columns:
        cleaned_data[column] = (
            cleaned_data[column]
            .astype("string")
            .str.strip()
        )

    # Remove completely duplicated rows.
    cleaned_data = cleaned_data.drop_duplicates()

    # Product ID and product name are required.
    required_columns = [
        column
        for column in ["product_id", "product_name"]
        if column in cleaned_data.columns
    ]

    for column in required_columns:
        cleaned_data[column] = cleaned_data[column].replace("", pd.NA)

    cleaned_data = cleaned_data.dropna(
        subset=required_columns
    )

    # Convert price columns to numbers.
    for column in ["discounted_price", "actual_price"]:
        if column in cleaned_data.columns:
            cleaned_data[column] = clean_currency(
                cleaned_data[column]
            )

            cleaned_data.loc[
                cleaned_data[column] < 0,
                column,
            ] = pd.NA

    # Convert the discount percentage to a number.
    if "discount_percentage" in cleaned_data.columns:
        cleaned_data["discount_percentage"] = clean_percentage(
            cleaned_data["discount_percentage"]
        )

        invalid_discount = ~cleaned_data[
            "discount_percentage"
        ].between(0, 100)

        cleaned_data.loc[
            invalid_discount,
            "discount_percentage",
        ] = pd.NA

    # Convert ratings to numbers.
    if "rating" in cleaned_data.columns:
        cleaned_data["rating"] = pd.to_numeric(
            cleaned_data["rating"],
            errors="coerce",
        )

        invalid_rating = ~cleaned_data["rating"].between(0, 5)

        cleaned_data.loc[
            invalid_rating,
            "rating",
        ] = pd.NA

    # Convert rating counts to integers.
    if "rating_count" in cleaned_data.columns:
        cleaned_data["rating_count"] = clean_count(
            cleaned_data["rating_count"]
        )

        cleaned_data.loc[
            cleaned_data["rating_count"] < 0,
            "rating_count",
        ] = pd.NA

    # Remove user identifiers because the project does not need them.
    cleaned_data = cleaned_data.drop(
        columns=["user_id", "user_name"],
        errors="ignore",
    )

    return cleaned_data.reset_index(drop=True)


def save_data(
    data: pd.DataFrame,
    processed_path: Optional[Path] = None,
    sample_path: Optional[Path] = None,
) -> None:
    """Save the cleaned intermediate data and a sample."""
    processed_path = PROCESSED_DATA_PATH if processed_path is None else processed_path
    sample_path = SAMPLE_DATA_PATH if sample_path is None else sample_path
    processed_path.parent.mkdir(parents=True, exist_ok=True)
    sample_path.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(processed_path, index=False)
    data.head(100).to_csv(sample_path, index=False)


def main() -> None:
    raw_data = load_data(RAW_DATA_PATH)
    cleaned_data = clean_data(raw_data)

    print(f"Rows before cleaning: {len(raw_data)}")
    print(f"Rows after cleaning:  {len(cleaned_data)}")
    print(
        "Removed rows:         "
        f"{len(raw_data) - len(cleaned_data)}"
    )

    numeric_columns = [
        "discounted_price",
        "actual_price",
        "discount_percentage",
        "rating",
        "rating_count",
    ]

    existing_columns = [
        column
        for column in numeric_columns
        if column in cleaned_data.columns
    ]

    print("\nNumeric column types:")
    print(cleaned_data[existing_columns].dtypes)

    print("\nMissing values:")
    print(cleaned_data[existing_columns].isna().sum())

    print("\nCleaned data preview:")
    print(cleaned_data[existing_columns].head())

    save_data(cleaned_data)

    print(f"\nProcessed data saved to: {PROCESSED_DATA_PATH}")
    print(f"Public sample saved to:  {SAMPLE_DATA_PATH}")


if __name__ == "__main__":
    main()
