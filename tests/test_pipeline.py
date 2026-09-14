import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd
import pytest

from src import clean_data as cleaning
from src import load_to_db as database
from src import pipeline


@pytest.fixture
def pipeline_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Path]:
    paths = {
        "raw": tmp_path / "raw" / "amazon.csv",
        "cleaned": tmp_path / "processed" / "cleaned_products.csv",
        "sample": tmp_path / "sample" / "cleaned_products_sample.csv",
        "database": tmp_path / "processed" / "products.db",
    }
    paths["raw"].parent.mkdir(parents=True)

    monkeypatch.setattr(cleaning, "RAW_DATA_PATH", paths["raw"])
    monkeypatch.setattr(cleaning, "PROCESSED_DATA_PATH", paths["cleaned"])
    monkeypatch.setattr(cleaning, "SAMPLE_DATA_PATH", paths["sample"])
    monkeypatch.setattr(database, "DATABASE_PATH", paths["database"])

    return paths


@pytest.fixture
def raw_products() -> pd.DataFrame:
    product = {
        "product_id": " P1 ",
        "product_name": " Keyboard ",
        "category": "Electronics",
        "discounted_price": "₹1,099",
        "actual_price": "₹1,500",
        "discount_percentage": "27%",
        "rating": "4.5",
        "rating_count": "100",
        "about_product": "Test product",
        "review_id": "R1",
        "review_title": "Test review",
        "review_content": "Synthetic review content.",
        "img_link": "https://example.com/image.jpg",
        "product_link": "https://example.com/product",
        "user_id": "TEST-USER",
        "user_name": "Demo Customer",
    }

    return pd.DataFrame([
        product,
        product.copy(),
        {**product, "rating_count": "500"},
        {
            **product,
            "product_id": "P2",
            "product_name": "Mouse",
            "rating": "|",
            "rating_count": None,
        },
    ])


@pytest.fixture
def existing_outputs(
    pipeline_paths: dict[str, Path],
) -> dict[str, bytes]:
    for key in ("cleaned", "sample"):
        path = pipeline_paths[key]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("previous output\n", encoding="utf-8")

    with closing(sqlite3.connect(pipeline_paths["database"])) as connection:
        with connection:
            connection.execute("CREATE TABLE sentinel (value TEXT)")
            connection.execute("INSERT INTO sentinel VALUES ('keep me')")

    return {
        key: pipeline_paths[key].read_bytes()
        for key in ("cleaned", "sample", "database")
    }


def assert_outputs_unchanged(
    paths: dict[str, Path],
    original: dict[str, bytes],
) -> None:
    for key, content in original.items():
        assert paths[key].read_bytes() == content, key


def test_pipeline_end_to_end(
    pipeline_paths: dict[str, Path],
    raw_products: pd.DataFrame,
    capsys: pytest.CaptureFixture,
) -> None:
    raw_products.to_csv(pipeline_paths["raw"], index=False)
    original_raw = pipeline_paths["raw"].read_bytes()

    summary = pipeline.run_pipeline()

    assert summary == {
        "raw_rows": 4,
        "cleaned_rows": 3,
        "removed_rows": 1,
        "duplicate_product_ids": 1,
        "database_rows": 2,
    }

    cleaned = pd.read_csv(pipeline_paths["cleaned"])
    sample = pd.read_csv(pipeline_paths["sample"])
    assert len(cleaned) == 3
    pd.testing.assert_frame_equal(sample, cleaned.head(100))
    assert "user_id" not in cleaned.columns
    assert "user_name" not in cleaned.columns
    assert cleaned.loc[0, "product_name"] == "Keyboard"
    assert cleaned.loc[0, "discounted_price"] == 1099

    # Exercise the command entry point and a second complete run.
    pipeline.main()
    output = capsys.readouterr().out
    assert "Pipeline completed successfully." in output
    assert "Database validation passed." in output

    with closing(sqlite3.connect(pipeline_paths["database"])) as connection:
        rows = connection.execute(
            """
            SELECT product_id, discounted_price, rating, rating_count
            FROM products
            ORDER BY product_id
            """
        ).fetchall()

    assert rows == [
        ("P1", 1099.0, 4.5, 500),
        ("P2", 1099.0, None, None),
    ]
    assert pipeline_paths["raw"].read_bytes() == original_raw


def test_pipeline_rejects_missing_source(
    pipeline_paths: dict[str, Path],
    existing_outputs: dict[str, bytes],
) -> None:
    with pytest.raises(FileNotFoundError, match="Dataset not found"):
        pipeline.run_pipeline()

    assert_outputs_unchanged(pipeline_paths, existing_outputs)


def test_pipeline_rejects_empty_input(
    pipeline_paths: dict[str, Path],
    raw_products: pd.DataFrame,
    existing_outputs: dict[str, bytes],
) -> None:
    raw_products.iloc[:0].to_csv(pipeline_paths["raw"], index=False)

    with pytest.raises(ValueError, match="contains no rows"):
        pipeline.run_pipeline()

    assert_outputs_unchanged(pipeline_paths, existing_outputs)


def test_pipeline_rejects_no_usable_products(
    pipeline_paths: dict[str, Path],
    raw_products: pd.DataFrame,
    existing_outputs: dict[str, bytes],
) -> None:
    raw_products.assign(product_id=None).to_csv(
        pipeline_paths["raw"],
        index=False,
    )

    with pytest.raises(ValueError, match="No usable products"):
        pipeline.run_pipeline()

    assert_outputs_unchanged(pipeline_paths, existing_outputs)


def test_pipeline_rejects_missing_columns(
    pipeline_paths: dict[str, Path],
    raw_products: pd.DataFrame,
    existing_outputs: dict[str, bytes],
) -> None:
    raw_products.drop(columns=["actual_price"]).to_csv(
        pipeline_paths["raw"],
        index=False,
    )

    with pytest.raises(ValueError, match="Missing columns"):
        pipeline.run_pipeline()

    assert_outputs_unchanged(pipeline_paths, existing_outputs)


def test_pipeline_rejects_row_count_mismatch(
    pipeline_paths: dict[str, Path],
    raw_products: pd.DataFrame,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    raw_products.to_csv(pipeline_paths["raw"], index=False)
    monkeypatch.setattr(
        database,
        "load_database",
        lambda data: len(data) - 1,
    )

    with pytest.raises(ValueError, match="expected 2, found 1"):
        pipeline.main()

    assert "Pipeline completed successfully." not in capsys.readouterr().out
