"""Opt-in integration tests use an isolated schema, never the default database."""

import os
import uuid
from pathlib import Path
import pytest
import psycopg
from psycopg import sql
from src import postgres_storage as db
from src.clean_data import clean_data, load_data
from src.load_to_db import prepare_data
from src.pipeline import run_pipeline
from src.query_data import load_analytics

pytestmark = pytest.mark.postgres
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def batch(monkeypatch):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a disposable test database.")
    schema = "test_" + uuid.uuid4().hex
    with psycopg.connect(url, autocommit=True) as con:
        con.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    monkeypatch.setenv(
        "DATABASE_URL",
        psycopg.conninfo.make_conninfo(url, options=f"-c search_path={schema}"),
    )
    try:
        yield prepare_data(
            clean_data(load_data(ROOT / "data/sample/amazon_sample.csv"))
        ).head(3)
    finally:
        with psycopg.connect(url, autocommit=True) as con:
            con.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
            )


def test_upsert_and_null(batch):
    assert db.load_database(batch) == 3
    changed = batch.head(1).copy()
    changed["rating"] = None
    changed["product_name"] = "Updated product"
    assert db.load_database(changed) == 1
    assert db.get_database_count() == 3
    result = load_analytics("postgres").set_index("product_id")
    assert result.loc[changed.iloc[0].product_id, "product_name"] == "Updated product"
    assert (
        result.loc[changed.iloc[0].product_id, "rating"]
        != result.loc[changed.iloc[0].product_id, "rating"]
    )


def test_rollback_and_read_only(batch):
    db.load_database(batch)
    invalid = batch.copy()
    invalid.loc[invalid.index[0], "product_name"] = "Must roll back"
    invalid.loc[invalid.index[-1], "rating"] = 8
    with pytest.raises(RuntimeError):
        db.load_database(invalid)
    assert "Must roll back" not in load_analytics("postgres").product_name.tolist()
    with pytest.raises(RuntimeError):
        with db.connect(read_only=True) as con:
            con.execute("DELETE FROM products")
    assert db.get_database_count() == 3


def test_postgres_pipeline(batch, tmp_path):
    result = run_pipeline(
        ROOT / "data/sample/amazon_sample.csv", tmp_path, backend="postgres"
    )
    assert result["batch_rows"] == result["database_rows"]
    assert len(load_analytics("postgres")) == result["database_rows"]
