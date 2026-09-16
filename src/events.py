"""Apply versioned product events safely, including retries and deletions."""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.catalog import Catalog
from src.load_to_db import DATABASE_COLUMNS
from src.privacy import redact
from src.validate_data import build_quality_report, require_quality


class ProductPayload(BaseModel):
    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, allow_inf_nan=False
    )
    product_name: str = Field(min_length=1, max_length=2000)
    category: str | None = Field(default=None, max_length=1000)
    about_product: str | None = Field(default=None, max_length=10000)
    discounted_price: float | None = Field(default=None, ge=0)
    actual_price: float | None = Field(default=None, ge=0)
    discount_percentage: float | None = Field(default=None, ge=0, le=100)
    rating: float | None = Field(default=None, ge=0, le=5)
    rating_count: int | None = Field(default=None, ge=0, le=2**63 - 1, strict=True)


class ProductEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    event_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    product_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    version: int = Field(gt=0, le=2**63 - 1, strict=True)
    operation: Literal["upsert", "delete"]
    product: ProductPayload | None = None
    stock_quantity: int | None = Field(default=None, ge=0, le=2**63 - 1, strict=True)

    @model_validator(mode="after")
    def check_operation(self):
        if self.operation == "upsert" and self.product is None:
            raise ValueError("Upsert requires a complete product payload.")
        if self.operation == "delete" and (
            self.product is not None or self.stock_quantity is not None
        ):
            raise ValueError("Delete must not contain product or inventory values.")
        return self


class EventConflict(ValueError):
    pass


def apply_event(event: ProductEvent, catalog=None):
    catalog = catalog or Catalog()
    identity = event.model_dump(mode="json")
    # Omitted inventory preserves stock; explicit null clears it. Retries must
    # distinguish those two requests even though the field value is None in both.
    identity["inventory_provided"] = "stock_quantity" in event.model_fields_set
    payload_hash = hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()
    ).hexdigest()
    record = None
    if event.operation == "upsert":
        record = dict.fromkeys(DATABASE_COLUMNS)
        record.update(event.product.model_dump())
        record["product_id"] = event.product_id
        for key in ("product_name", "category", "about_product"):
            if record[key] is not None:
                record[key] = redact(record[key])
        require_quality(build_quality_report(pd.DataFrame([record])))

    with catalog.connection(write=True) as con:
        if catalog.settings.backend == "postgres":
            # Serialize the version check with all other catalog writes.
            con.execute(
                "SELECT revision FROM catalog_state WHERE singleton=1 FOR UPDATE"
            )
        previous = catalog.execute(
            con,
            "SELECT payload_hash, outcome FROM processed_events WHERE event_id=?",
            (event.event_id,),
        ).fetchone()
        if previous:
            if previous[0] != payload_hash:
                raise EventConflict(
                    "This event ID was already used for a different payload."
                )
            return {
                "event_id": event.event_id,
                "status": "duplicate",
                "original_status": previous[1],
            }
        current = catalog.execute(
            con,
            "SELECT source_version FROM product_versions WHERE product_id=?",
            (event.product_id,),
        ).fetchone()
        outcome = "stale" if current and event.version <= current[0] else "applied"
        if outcome == "applied":
            if event.operation == "delete":
                catalog.execute(
                    con, "DELETE FROM products WHERE product_id=?", (event.product_id,)
                )
            else:
                columns = ", ".join(DATABASE_COLUMNS)
                marks = ", ".join("?" for _ in DATABASE_COLUMNS)
                updates = ", ".join(
                    f"{c}=excluded.{c}" for c in DATABASE_COLUMNS if c != "product_id"
                )
                catalog.execute(
                    con,
                    f"INSERT INTO products ({columns}) VALUES ({marks}) ON CONFLICT(product_id) DO UPDATE SET {updates}",
                    tuple(record[c] for c in DATABASE_COLUMNS),
                )
                # Omitted stock means "no inventory update"; explicit null means unknown.
                if "stock_quantity" in event.model_fields_set:
                    catalog.execute(
                        con,
                        """INSERT INTO inventory(product_id, stock_quantity) VALUES (?, ?)
                        ON CONFLICT(product_id) DO UPDATE SET stock_quantity=excluded.stock_quantity""",
                        (event.product_id, event.stock_quantity),
                    )
            catalog.execute(
                con,
                """INSERT INTO product_versions(product_id, source_version) VALUES (?, ?)
                ON CONFLICT(product_id) DO UPDATE SET source_version=excluded.source_version""",
                (event.product_id, event.version),
            )
        catalog.execute(
            con,
            """INSERT INTO processed_events
            (event_id, payload_hash, product_id, source_version, outcome) VALUES (?, ?, ?, ?, ?)""",
            (event.event_id, payload_hash, event.product_id, event.version, outcome),
        )
        revision = con.execute(
            "SELECT revision FROM catalog_state WHERE singleton=1"
        ).fetchone()[0]
    return {"event_id": event.event_id, "status": outcome, "catalog_revision": revision}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "file", type=Path, help="JSONL events; committed individually, safe to replay"
    )
    args = parser.parse_args(argv)
    for line in args.file.read_text(encoding="utf-8").splitlines():
        if line.strip():
            print(json.dumps(apply_event(ProductEvent.model_validate_json(line))))


if __name__ == "__main__":
    main()
