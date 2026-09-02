import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from src import load_to_db
from src.load_to_db import (
    DATABASE_COLUMNS,
    prepare_data,
    validate_columns,
)


def make_product(
    product_id: str,
    rating_count: int = 100,
) -> dict:
    """Create a complete product for testing."""

    return {
        "product_id": product_id,
        "product_name": f"Product {product_id}",
        "category": "Electronics",
        "discounted_price": 100.0,
        "actual_price": 150.0,
        "discount_percentage": 33.0,
        "rating": 4.5,
        "rating_count": rating_count,
        "about_product": "Test product",
        "review_id": f"R-{product_id}",
        "review_title": "Good product",
        "review_content": "This is a test review.",
        "img_link": "https://example.com/image.jpg",
        "product_link": "https://example.com/product",
    }


def test_validate_columns_rejects_missing_columns() -> None:
    incomplete_data = pd.DataFrame({
        "product_id": ["P1"],
        "product_name": ["Product P1"],
    })

    with pytest.raises(
        ValueError,
        match="Missing columns",
    ):
        validate_columns(incomplete_data)


def test_prepare_data_keeps_best_duplicate() -> None:
    data = pd.DataFrame([
        make_product("P1", rating_count=100),
        make_product("P1", rating_count=500),
    ])

    prepared_data = prepare_data(data)

    assert len(prepared_data) == 1
    assert prepared_data.iloc[0]["product_id"] == "P1"
    assert prepared_data.iloc[0]["rating_count"] == 500
    assert prepared_data.columns.tolist() == DATABASE_COLUMNS


def test_load_database_creates_products_table(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    temporary_database = tmp_path / "products.db"

    monkeypatch.setattr(
        load_to_db,
        "DATABASE_PATH",
        temporary_database,
    )

    data = pd.DataFrame([
        make_product("P1"),
        make_product("P2"),
    ])

    inserted_count = load_to_db.load_database(data)

    assert inserted_count == 2
    assert temporary_database.exists()

    with sqlite3.connect(
        temporary_database
    ) as connection:
        database_count = connection.execute(
            "SELECT COUNT(*) FROM products"
        ).fetchone()[0]

        product_ids = connection.execute(
            """
            SELECT product_id
            FROM products
            ORDER BY product_id
            """
        ).fetchall()

    assert database_count == 2
    assert product_ids == [("P1",), ("P2",)]