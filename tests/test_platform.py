import json
import os
import sqlite3
import uuid
from dataclasses import replace

import pandas as pd
import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql

from src.api import create_app
from src.catalog import Catalog
from src.config import Settings
from src.events import EventConflict, ProductEvent, apply_event
from src.load_to_db import DATABASE_COLUMNS, load_database
from src.monitor import monitor
from src.predict import CategoryModel
from src.qa import answer
from src.search import SearchService
from src.train_model import train, prepare_training_data


@pytest.fixture
def rows():
    result = []
    for category, names in {
        "Electronics": ["wireless headphones", "bluetooth speaker", "phone charger"],
        "Home": ["cotton towel", "kitchen pan", "wooden table"],
    }.items():
        for index in range(12):
            row = dict.fromkeys(DATABASE_COLUMNS)
            row.update(
                product_id=f"{category}-{index}",
                product_name=f"{names[index % 3]} model {index}",
                category=category + "|Items",
                discounted_price=10.0,
                actual_price=20.0,
                discount_percentage=50.0,
                rating=4.0,
                rating_count=20,
                about_product="Contact seller@example.com for details",
                review_content="DO NOT EXPOSE THIS REVIEW",
            )
            result.append(row)
    return pd.DataFrame(result)


@pytest.fixture(params=["sqlite", pytest.param("postgres", marks=pytest.mark.postgres)])
def catalog(request, rows, tmp_path, monkeypatch):
    settings = Settings(
        backend=request.param,
        database_path=tmp_path / "products.db",
        model_path=tmp_path / "model/model.json",
        report_dir=tmp_path / "model",
        api_key="test-only-key",
    )
    if request.param == "sqlite":
        load_database(rows, settings.database_path)
        yield Catalog(settings)
    else:
        url = os.environ.get("TEST_DATABASE_URL")
        if not url:
            pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration.")
        schema = "platform_" + uuid.uuid4().hex
        with psycopg.connect(url, autocommit=True) as con:
            con.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        monkeypatch.setenv(
            "DATABASE_URL",
            psycopg.conninfo.make_conninfo(url, options=f"-c search_path={schema}"),
        )
        try:
            from src.postgres_storage import load_database as load_postgres

            load_postgres(rows)
            yield Catalog(settings)
        finally:
            with psycopg.connect(url, autocommit=True) as con:
                con.execute(
                    sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
                )


def event(version=1, operation="upsert", **kwargs):
    data = {
        "event_id": f"event-{version}-{operation}",
        "product_id": "NEW-1",
        "version": version,
        "operation": operation,
    }
    if operation == "upsert":
        data.update(
            product={
                "product_name": "Solar camping lantern",
                "category": "Home",
                "discounted_price": 15,
                "actual_price": 20,
            },
            stock_quantity=3,
        )
    return ProductEvent.model_validate({**data, **kwargs})


def test_event_retry_ordering_delete_and_search_refresh(catalog):
    search = SearchService(catalog)
    old = search.current().revision
    first = apply_event(event(), catalog)
    assert first["status"] == "applied"
    assert first["catalog_revision"] > old
    assert search.search("NEW-1")[0]["product_name"] == "Solar camping lantern"
    assert apply_event(event(), catalog)["status"] == "duplicate"
    assert catalog.revision() == first["catalog_revision"]
    apply_event(event(3, "delete"), catalog)
    assert apply_event(event(2), catalog)["status"] == "stale"
    assert not search.search("NEW-1")
    assert apply_event(event(4), catalog)["status"] == "applied"
    assert search.search("NEW-1", in_stock=True)


def test_reused_event_id_conflicts(catalog):
    apply_event(event(), catalog)
    with pytest.raises(EventConflict):
        apply_event(event(stock_quantity=9), catalog)


def test_omitted_inventory_differs_from_explicit_null(catalog):
    apply_event(event(), catalog)
    payload = event(2).model_dump()
    payload.pop("stock_quantity")
    without_stock = ProductEvent.model_validate(payload)
    apply_event(without_stock, catalog)
    assert SearchService(catalog).search("NEW-1")[0]["stock_quantity"] == 3
    with pytest.raises(EventConflict):
        apply_event(
            ProductEvent.model_validate({**payload, "stock_quantity": None}), catalog
        )
    apply_event(event(3, stock_quantity=None), catalog)
    assert SearchService(catalog).search("NEW-1")[0]["stock_quantity"] is None


def test_event_transaction_rolls_back(catalog, monkeypatch):
    original = catalog.execute
    revision = catalog.revision()

    def fail_late(con, statement, values=()):
        if "INSERT INTO processed_events" in statement:
            raise RuntimeError("simulated failure after product write")
        return original(con, statement, values)

    monkeypatch.setattr(catalog, "execute", fail_late)
    with pytest.raises(RuntimeError):
        apply_event(event(), catalog)
    assert catalog.revision() == revision
    assert not SearchService(catalog).search("NEW-1")
    monkeypatch.setattr(catalog, "execute", original)
    assert apply_event(event(), catalog)["status"] == "applied"


def test_change_feed_snapshot_and_privacy(catalog):
    revision, products = catalog.snapshot()
    assert revision == len(products)
    assert "[email removed]" in products[0]["about_product"]
    assert "review_content" not in products[0]
    first = catalog.changes(0, 3)
    second = catalog.changes(first[-1]["change_id"], 3)
    assert first[-1]["change_id"] < second[0]["change_id"]
    with pytest.raises((sqlite3.OperationalError, RuntimeError)):
        with catalog.connection() as con:
            con.execute("DELETE FROM products")


def test_search_exact_code_filters_and_empty_query(catalog):
    search = SearchService(catalog)
    assert (
        search.search("Tell me about Electronics-0")[0]["product_id"] == "Electronics-0"
    )
    assert search.search("headphones")[0]["main_category"] == "Electronics"
    assert not search.search("headphones", max_price=1)
    assert not search.search("headphones", in_stock=True)
    assert not search.search("zxqvbnmzzz")
    with pytest.raises(ValueError):
        search.search(" ")


def test_factual_answer_unknown_stock_and_missing_evidence(catalog):
    search = SearchService(catalog)
    result = answer("Electronics-0", search)
    assert "stock unknown" in result["answer"]
    assert "Electronics-0" in result["source_ids"]
    assert not result["generated"]
    assert "DO NOT EXPOSE" not in json.dumps(result)
    assert not answer("zxqvbnmzzz", search)["sources"]


def test_ollama_checks_citations_and_falls_back(catalog, monkeypatch):
    search = SearchService(catalog)
    settings = replace(
        catalog.settings, ollama_url="http://localhost:11434", ollama_model="test-model"
    )
    import httpx

    def invalid(*args, **kwargs):
        assert "DO NOT EXPOSE" not in json.dumps(kwargs["json"])
        return httpx.Response(
            200,
            request=httpx.Request("POST", args[0]),
            json={
                "response": json.dumps(
                    {"answer": "Unsupported", "source_ids": ["FAKE"]}
                )
            },
        )

    monkeypatch.setattr("src.qa.httpx.post", invalid)
    result = answer("Electronics-0", search, "ollama", settings)
    assert not result["generated"]
    assert "invalid citations" in result["notice"]

    def valid(*args, **kwargs):
        return httpx.Response(
            200,
            request=httpx.Request("POST", args[0]),
            json={
                "response": json.dumps(
                    {
                        "answer": "The stored price is INR 10.",
                        "source_ids": ["Electronics-0"],
                    }
                )
            },
        )

    monkeypatch.setattr("src.qa.httpx.post", valid)
    assert answer("Electronics-0", search, "ollama", settings)["generated"]


def test_api_auth_validation_and_update_flow(catalog):
    client = TestClient(create_app(catalog.settings))
    assert client.get("/ready").status_code == 200
    payload = event().model_dump(exclude_unset=True)
    assert client.post("/events", json=payload).status_code == 401
    assert (
        client.post("/events", json=payload, headers={"X-API-Key": "wrong"}).status_code
        == 401
    )
    assert (
        client.post(
            "/events", json=payload, headers={"X-API-Key": "test-only-key"}
        ).json()["status"]
        == "applied"
    )
    assert client.get("/products/NEW-1").json()["product"]["stock_quantity"] == 3
    assert (
        client.get("/search", params={"q": "NEW-1", "in_stock": True}).json()[
            "results"
        ][0]["product_id"]
        == "NEW-1"
    )
    assert client.get("/products", params={"limit": 1}).json()["total"] == 25
    assert client.get("/products/missing").status_code == 404
    assert client.get("/search", params={"q": "", "limit": 1000}).status_code == 422
    invalid = client.post(
        "/predict", json={"product_name": "", "secret": "private-value"}
    )
    assert invalid.status_code == 422 and "private-value" not in invalid.text
    assert (
        client.post("/predict", json={"product_name": "phone charger"}).status_code
        == 503
    )
    assert "platform_requests_total" in client.get("/metrics").text


def test_write_access_disabled_without_key(catalog):
    client = TestClient(create_app(replace(catalog.settings, api_key="")))
    assert client.post("/events", json=event().model_dump()).status_code == 503


def test_model_splits_serialization_and_api(rows, tmp_path):
    path = tmp_path / "training.csv"
    rows.to_csv(path, index=False)
    report = train(path, tmp_path / "model")
    split = [
        set(report["split_product_ids"][name])
        for name in ("train", "validation", "test")
    ]
    assert (
        not split[0] & split[1] and not split[0] & split[2] and not split[1] & split[2]
    )
    model = CategoryModel(tmp_path / "model/model.json")
    assert model.predict("wireless headphones")["category"] == "Electronics"
    assert model.predict("zxqvbnmzzz")["abstained"]
    assert sum(
        model.predict("cotton towel")["probabilities"].values()
    ) == pytest.approx(1, abs=1e-5)
    report2 = train(path, tmp_path / "second")
    assert report["test"] == report2["test"]
    assert report["data_sha256"] == report2["data_sha256"]
    settings = Settings(model_path=tmp_path / "model/model.json")
    client = TestClient(create_app(settings))
    assert (
        client.post("/predict", json={"product_name": "wooden table"}).json()[
            "category"
        ]
        == "Home"
    )


def test_duplicate_names_and_rare_labels(rows):
    duplicate = rows.iloc[0].copy()
    duplicate["product_id"] = "extra"
    rare = rows.iloc[0].copy()
    rare["product_id"], rare["product_name"], rare["category"] = (
        "rare",
        "rare isolated name",
        "Rare",
    )
    prepared, excluded = prepare_training_data(
        pd.concat([rows, pd.DataFrame([duplicate, rare])])
    )
    assert prepared.name_key.is_unique
    assert excluded == {"Rare": 1}
    with pytest.raises(ValueError):
        prepare_training_data(rows.head(2))


def test_monitor_reports_unknown_inventory_and_shift(catalog, rows, tmp_path):
    path = tmp_path / "training.csv"
    rows.to_csv(path, index=False)
    train(path, tmp_path / "model")
    model = CategoryModel(tmp_path / "model/model.json")
    report = monitor(catalog, model)
    assert report["unknown_inventory"] == 24
    assert report["category_total_variation"] == 0
    for index in range(12):
        apply_event(
            ProductEvent(
                event_id=f"delete-{index}",
                product_id=f"Home-{index}",
                version=1,
                operation="delete",
            ),
            catalog,
        )
    assert monitor(catalog, model)["alerts"]


def test_concurrent_event_versions_finish_at_newest(catalog):
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=3) as pool:
        list(
            pool.map(
                lambda version: apply_event(
                    event(version, stock_quantity=version), catalog
                ),
                [2, 5, 1, 4, 3],
            )
        )
    product = SearchService(catalog).search("NEW-1")[0]
    assert product["stock_quantity"] == 5
    assert apply_event(event(5, stock_quantity=5), catalog)["status"] == "duplicate"


def test_multiclass_json_artifact_matches_report(rows, tmp_path):
    from sklearn.metrics import accuracy_score, f1_score

    extra = rows.head(8).copy()
    extra["product_id"] = [f"books-{index}" for index in range(8)]
    extra["product_name"] = [
        f"paperback history book edition {index}" for index in range(8)
    ]
    extra["category"] = "Books"
    data = pd.concat([rows, extra], ignore_index=True)
    path = tmp_path / "training.csv"
    data.to_csv(path, index=False)
    report = train(path, tmp_path / "model")
    fitted = CategoryModel(tmp_path / "model/model.json")
    test = data.set_index("product_id").loc[report["split_product_ids"]["test"]]
    truth = test.category.str.split("|").str[0]
    predicted = [fitted.predict(name)["category"] for name in test.product_name]
    assert accuracy_score(truth, predicted) == report["test"]["accuracy"]
    assert f1_score(truth, predicted, average="macro") == report["test"]["macro_f1"]
