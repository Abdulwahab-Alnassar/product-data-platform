from pathlib import Path
import pandas as pd
from streamlit.testing.v1 import AppTest
from src.query_data import export_csv, filter_products, load_analytics
from src.pipeline import run_pipeline

ROOT = Path(__file__).resolve().parents[1]


def test_filters_and_safe_export():
    data = pd.DataFrame(
        {
            "product_id": ["1", "2"],
            "product_name": ["=SUM(A1)", "Phone"],
            "main_category": ["A", "B"],
            "rating": [None, 4.5],
        }
    )
    assert len(filter_products(data, search="Phone", min_rating=4)) == 1
    assert len(filter_products(data, include_unrated=False)) == 1
    assert filter_products(data, search="[").empty
    assert "'=SUM(A1)" in export_csv(data).decode("utf-8-sig")


def test_dashboard(tmp_path, monkeypatch):
    run_pipeline(ROOT / "data/sample/amazon_sample.csv", tmp_path)
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "products.db"))
    monkeypatch.setenv("DASHBOARD_BACKEND", "sqlite")
    data = load_analytics(database_path=tmp_path / "products.db")
    assert len(data) > 0
    app = AppTest.from_file(str(ROOT / "dashboard.py")).run(timeout=30)
    assert not app.exception
    app.sidebar.text_input[0].set_value("NONEXISTENT_PRODUCT_12345").run()
    assert not app.exception
    assert app.metric[0].value == "0"


def test_dashboard_missing_database(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "missing.db"))
    monkeypatch.setenv("DASHBOARD_BACKEND", "sqlite")
    app = AppTest.from_file(str(ROOT / "dashboard.py")).run(timeout=30)
    assert not app.exception
    assert len(app.error) == 1
    assert not (tmp_path / "missing.db").exists()
