import pandas as pd

from src.clean_data import (
    clean_count,
    clean_currency,
    clean_data,
    clean_percentage,
)


def test_clean_currency() -> None:
    values = pd.Series([
        "₹1,099",
        " ₹399 ",
        "invalid",
    ])

    result = clean_currency(values)

    assert result.iloc[0] == 1099
    assert result.iloc[1] == 399
    assert pd.isna(result.iloc[2])


def test_clean_percentage() -> None:
    values = pd.Series([
        "64%",
        " 10% ",
        "invalid",
    ])

    result = clean_percentage(values)

    assert result.iloc[0] == 64
    assert result.iloc[1] == 10
    assert pd.isna(result.iloc[2])


def test_clean_count() -> None:
    values = pd.Series([
        "24,269",
        " 1,000 ",
        "invalid",
    ])

    result = clean_count(values)

    assert result.iloc[0] == 24269
    assert result.iloc[1] == 1000
    assert pd.isna(result.iloc[2])
    assert str(result.dtype) == "Int64"


def test_clean_data_pipeline() -> None:
    valid_product = {
        " Product_ID ": " P1 ",
        "Product_Name": " Keyboard ",
        "discounted_price": "₹1,099",
        "actual_price": "₹1,500",
        "discount_percentage": "27%",
        "rating": "4.5",
        "rating_count": "2,000",
        "user_id": "USER1",
        "user_name": "Test User",
    }

    invalid_product = {
        " Product_ID ": "P2",
        "Product_Name": "Mouse",
        "discounted_price": "-10",
        "actual_price": "-20",
        "discount_percentage": "150%",
        "rating": "7",
        "rating_count": "-5",
        "user_id": "USER2",
        "user_name": "Another User",
    }

    missing_product_id = {
        " Product_ID ": None,
        "Product_Name": "Monitor",
        "discounted_price": "₹500",
        "actual_price": "₹700",
        "discount_percentage": "20%",
        "rating": "4",
        "rating_count": "100",
        "user_id": "USER3",
        "user_name": "Missing ID",
    }

    raw_data = pd.DataFrame([
        valid_product,
        valid_product.copy(),
        invalid_product,
        missing_product_id,
    ])

    cleaned_data = clean_data(raw_data)

    # Duplicate and missing-ID rows must be removed.
    assert len(cleaned_data) == 2
    assert cleaned_data["product_id"].tolist() == ["P1", "P2"]

    # Text and numeric values must be cleaned.
    products = cleaned_data.set_index("product_id")

    assert products.loc["P1", "product_name"] == "Keyboard"
    assert products.loc["P1", "discounted_price"] == 1099
    assert products.loc["P1", "actual_price"] == 1500
    assert products.loc["P1", "discount_percentage"] == 27
    assert products.loc["P1", "rating"] == 4.5
    assert products.loc["P1", "rating_count"] == 2000

    # Invalid values must become missing values.
    assert pd.isna(products.loc["P2", "discounted_price"])
    assert pd.isna(products.loc["P2", "actual_price"])
    assert pd.isna(products.loc["P2", "discount_percentage"])
    assert pd.isna(products.loc["P2", "rating"])
    assert pd.isna(products.loc["P2", "rating_count"])

    # User identifiers must not remain.
    assert "user_id" not in cleaned_data.columns
    assert "user_name" not in cleaned_data.columns