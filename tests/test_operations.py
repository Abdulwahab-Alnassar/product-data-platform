import json
import sqlite3
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.backup import copy_database
from src.config import Settings
from src.pipeline import run_pipeline
from src.train_model import train

ROOT = Path(__file__).resolve().parents[1]


def test_latest_run_marks_early_failure(tmp_path):
    run_pipeline(ROOT / "data/sample/amazon_sample.csv", tmp_path)
    quality = json.loads((tmp_path / "quality_report.json").read_text())
    run = json.loads((tmp_path / "run_report.json").read_text())
    assert run["status"] == "completed" and run["run_id"] == quality["run_id"]
    with pytest.raises(FileNotFoundError):
        run_pipeline(tmp_path / "missing.csv", tmp_path)
    failed = json.loads((tmp_path / "run_report.json").read_text())
    assert failed["status"] == "failed" and failed["run_id"] != quality["run_id"]


def test_backup_restore_preserves_data_and_refuses_overwrite(tmp_path):
    run_pipeline(ROOT / "data/sample/amazon_sample.csv", tmp_path)
    backup = tmp_path / "snapshot.backup"
    restored = tmp_path / "restored.db"
    copy_database(tmp_path / "products.db", backup)
    copy_database(backup, restored)
    with sqlite3.connect(restored) as con:
        assert con.execute("SELECT count(*) FROM products").fetchone()[0] == 100
        assert con.execute("SELECT revision FROM catalog_state").fetchone()[0] == 100
    with pytest.raises(FileExistsError):
        copy_database(backup, restored)


def test_settings_environment_and_secret_repr(monkeypatch):
    monkeypatch.setenv("PLATFORM_BACKEND", "sqlite")
    monkeypatch.setenv("PLATFORM_API_KEY", "do-not-display")
    assert "do-not-display" not in repr(Settings.from_env())
    monkeypatch.setenv("PLATFORM_BACKEND", "invalid")
    with pytest.raises(ValueError):
        Settings.from_env()


def test_dashboard_prediction_search_qa_and_health(tmp_path, monkeypatch):
    run_pipeline(ROOT / "data/sample/amazon_sample.csv", tmp_path)
    train(tmp_path / "cleaned_products.csv", tmp_path / "model")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "products.db"))
    monkeypatch.setenv("MODEL_PATH", str(tmp_path / "model/model.json"))
    monkeypatch.setenv("PLATFORM_BACKEND", "sqlite")
    app = AppTest.from_file(str(ROOT / "dashboard.py")).run(timeout=30)
    for label, value, button in [
        ("Product name to classify", "USB charging cable", "Predict category"),
        (
            "Search catalog by meaning, words, or product ID",
            "B07JW9H4J1",
            "Find products",
        ),
        (
            "Ask about a product; include its name or ID",
            "B07JW9H4J1",
            "Answer from catalog",
        ),
    ]:
        next(item for item in app.text_input if item.label == label).set_value(value)
        next(item for item in app.button if item.label == button).click().run(
            timeout=30
        )
        assert not app.exception and not app.error
    next(item for item in app.button if item.label == "Check data health").click().run(
        timeout=30
    )
    assert not app.exception and not app.error
