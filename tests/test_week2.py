import json
import logging
import sqlite3
import subprocess
import sys
from contextlib import closing

import pandas as pd
import pytest

from src import clean_data, load_to_db, pipeline
from src.logging_utils import pipeline_logging
from src.validate_data import build_quality_report, require_quality, save_quality_report


@pytest.fixture
def product():
    return {
        "product_id": "P1", "product_name": "Keyboard",
        "category": "Electronics|Accessories",
        "discounted_price": 100.0, "actual_price": 150.0,
        "discount_percentage": 33.0, "rating": 4.5, "rating_count": 200,
        "about_product": "Synthetic product", "review_id": "R1",
        "review_title": "Review", "review_content": "Synthetic review",
        "img_link": "https://example.com/image",
        "product_link": "https://example.com/product",
    }


def test_quality_accepts_valid_data(product):
    report = build_quality_report(pd.DataFrame([product]))
    require_quality(report)
    assert report["status"] == "passed"
    assert report["warning_checks"] == 0


@pytest.mark.parametrize("column,value", [
    ("product_id", " "),
    ("product_name", None),
    ("discounted_price", -1),
    ("actual_price", float("inf")),
    ("rating", 6),
    ("rating", "invalid"),
    ("discount_percentage", 101),
    ("rating_count", 1.5),
    ("rating_count", -1),
])
def test_quality_rejects_invalid_values(product, column, value):
    report = build_quality_report(pd.DataFrame([{**product, column: value}]))
    with pytest.raises(ValueError, match="Data quality failed"):
        require_quality(report)


def test_quality_rejects_price_inversion(product):
    data = pd.DataFrame([{**product, "discounted_price": 151}])
    report = build_quality_report(data)
    assert any(
        check["name"] == "discounted_price_not_above_actual" and not check["passed"]
        for check in report["checks"]
    )
    with pytest.raises(ValueError):
        require_quality(report)


def test_quality_reports_missing_columns_and_empty_data():
    report = build_quality_report(pd.DataFrame())
    assert "product_id" in report["missing_columns"]
    assert report["rows_checked"] == 0
    with pytest.raises(ValueError):
        require_quality(report)


def test_quality_rejects_duplicate_ids(product):
    report = build_quality_report(pd.DataFrame([product, product]))
    with pytest.raises(ValueError, match="unique_product_ids"):
        require_quality(report)


@pytest.mark.parametrize("in_source", [False, True])
def test_quality_rejects_identifiers(product, in_source):
    data = pd.DataFrame([product])
    if in_source:
        report = build_quality_report(data, source_columns=["user_id"])
    else:
        data["user_name"] = "Private name"
        report = build_quality_report(data)
    with pytest.raises(ValueError, match="no_user_identifiers"):
        require_quality(report)


def test_missing_values_are_warnings_and_report_has_no_rows(product, tmp_path):
    data = pd.DataFrame([{**product, "rating": None}])
    report = build_quality_report(data)
    require_quality(report)
    assert report["warning_checks"] == 1
    path = tmp_path / "quality.json"
    save_quality_report(report, path)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved == report
    assert "Keyboard" not in path.read_text(encoding="utf-8")


def test_clean_count_handles_fractional_and_infinite_values():
    result = clean_data.clean_count(pd.Series(["1.5", "inf", "1,000", None]))
    assert result.isna().tolist() == [True, True, False, True]
    assert result.iloc[2] == 1000


def test_cleaning_removes_blank_identity(product):
    data = pd.DataFrame([product, {**product, "product_id": " "}])
    assert len(clean_data.clean_data(data)) == 1


def test_upsert_updates_and_preserves_absent_products(product, tmp_path):
    path = tmp_path / "products.db"
    first = pd.DataFrame([product, {**product, "product_id": "P2"}])
    assert load_to_db.load_database(first, path) == 2
    updated = {**product, "discounted_price": 90.0, "rating": None}
    assert load_to_db.load_database(pd.DataFrame([updated]), path) == 1
    assert load_to_db.load_database(pd.DataFrame([updated]), path) == 1
    assert load_to_db.get_database_count(path) == 2
    with closing(sqlite3.connect(path)) as con:
        rows = con.execute(
            "SELECT product_id, discounted_price, rating FROM products ORDER BY product_id"
        ).fetchall()
    assert rows == [("P1", 90.0, None), ("P2", 100.0, 4.5)]


def test_failed_batch_rolls_back_prior_updates(product, tmp_path):
    path = tmp_path / "products.db"
    load_to_db.load_database(pd.DataFrame([product]), path)
    batch = pd.DataFrame([
        {**product, "product_name": "Changed"},
        {**product, "product_id": "P2", "rating": 6},
    ])
    with pytest.raises(sqlite3.IntegrityError):
        load_to_db.load_database(batch, path)
    with closing(sqlite3.connect(path)) as con:
        assert con.execute(
            "SELECT product_id, product_name FROM products"
        ).fetchall() == [("P1", "Keyboard")]


@pytest.mark.parametrize("kind", ["empty", "duplicate", "blank"])
def test_loader_rejects_bad_batches_before_writing(product, tmp_path, kind):
    path = tmp_path / "products.db"
    load_to_db.load_database(pd.DataFrame([product]), path)
    if kind == "empty":
        batch = pd.DataFrame([product]).iloc[:0]
    elif kind == "duplicate":
        batch = pd.DataFrame([product, product])
    else:
        batch = pd.DataFrame([{**product, "product_id": " "}])
    with pytest.raises(ValueError):
        load_to_db.load_database(batch, path)
    assert load_to_db.get_database_count(path) == 1


def test_views_rank_ties_and_calculate_inr_savings(product, tmp_path):
    path = tmp_path / "products.db"
    load_to_db.load_database(pd.DataFrame([
        product,
        {**product, "product_id": "P2"},
        {**product, "product_id": "P3", "rating": 3.5},
        {**product, "product_id": "P4", "rating": None},
        {**product, "product_id": "P5", "category": "Home", "rating": 5},
    ]), path)
    with closing(sqlite3.connect(path)) as con:
        assert con.execute(
            "SELECT product_id, rating_rank FROM category_product_rankings ORDER BY product_id"
        ).fetchall() == [("P1", 1), ("P2", 1), ("P3", 2), ("P4", None), ("P5", 1)]
        assert con.execute(
            "SELECT savings_inr, main_category FROM product_analytics WHERE product_id = 'P1'"
        ).fetchone() == (50.0, "Electronics")
        sql = (load_to_db.PROJECT_ROOT / "sql" / "advanced_queries.sql").read_text()
        statements = [part for part in sql.split(";") if part.strip()]
        assert len(statements) == 5
        for statement in statements:
            con.execute(statement).fetchall()


def test_pipeline_handles_smaller_second_batch(product, tmp_path):
    raw = tmp_path / "input.csv"
    output = tmp_path / "output"
    pd.DataFrame([product, {**product, "product_id": "P2"}]).to_csv(raw, index=False)
    pipeline.run_pipeline(raw, output)
    pd.DataFrame([{**product, "discounted_price": 80}]).to_csv(raw, index=False)
    summary = pipeline.run_pipeline(raw, output)
    assert summary["batch_rows"] == 1
    assert summary["database_rows"] == 2
    report = json.loads((output / "quality_report.json").read_text())
    assert report["rows_checked"] == 1


def test_pipeline_quality_failure_preserves_data_outputs(product, tmp_path):
    raw = tmp_path / "input.csv"
    output = tmp_path / "output"
    pd.DataFrame([product]).to_csv(raw, index=False)
    pipeline.run_pipeline(raw, output)
    files = [output / name for name in (
        "products.db", "cleaned_products.csv", "cleaned_products_sample.csv"
    )]
    before = [path.read_bytes() for path in files]
    pd.DataFrame([{**product, "discounted_price": 200}]).to_csv(raw, index=False)
    with pytest.raises(ValueError, match="Data quality failed"):
        pipeline.run_pipeline(raw, output)
    assert [path.read_bytes() for path in files] == before
    assert json.loads((output / "quality_report.json").read_text())["status"] == "failed"


def test_logging_does_not_duplicate_handlers(tmp_path, capsys):
    path = tmp_path / "pipeline.log"
    logger = logging.getLogger("product_data_platform")
    original = list(logger.handlers)
    for _ in range(2):
        with pipeline_logging(path) as configured:
            configured.info("test-event")
    assert path.read_text().count("test-event") == 2
    assert capsys.readouterr().out.count("test-event") == 2
    assert logger.handlers == original


def test_cli_failure_is_logged_and_returns_nonzero(tmp_path):
    output = tmp_path / "output"
    result = subprocess.run([
        sys.executable, "-m", "src.pipeline",
        "--input", str(tmp_path / "missing.csv"),
        "--output-dir", str(output),
    ], cwd=load_to_db.PROJECT_ROOT, capture_output=True, text=True)
    assert result.returncode != 0
    assert "Pipeline failed" in (output / "pipeline.log").read_text()
    assert not (output / "products.db").exists()
