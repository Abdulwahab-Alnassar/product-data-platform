"""Quality checks for the prepared batch; reports contain counts, not rows."""

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

from src.load_to_db import DATABASE_COLUMNS

NUMERIC_COLUMNS = (
    "discounted_price", "actual_price", "discount_percentage",
    "rating", "rating_count",
)


def build_quality_report(
    data: pd.DataFrame,
    source_columns: Optional[Iterable[str]] = None,
) -> dict:
    checks = []

    def check(name: str, invalid_count: int, severity: str = "error"):
        checks.append({
            "name": name,
            "severity": severity,
            "invalid_count": int(invalid_count),
            "passed": int(invalid_count) == 0,
        })

    missing = set(DATABASE_COLUMNS) - set(data.columns)
    check("required_columns", len(missing))
    check("nonempty_batch", int(data.empty))
    columns = set(data.columns)
    if source_columns is not None:
        columns.update(source_columns)
    check("no_user_identifiers", len(columns & {"user_id", "user_name"}))

    for name in ("product_id", "product_name"):
        if name in data:
            text = data[name].astype("string").str.strip()
            check(name + "_present", (text.isna() | text.eq("")).sum())
    if "product_id" in data:
        ids = data["product_id"].astype("string").str.strip()
        check("unique_product_ids", ids.duplicated().sum())

    numeric = {}
    for name in NUMERIC_COLUMNS:
        if name not in data:
            continue
        values = pd.to_numeric(data[name], errors="coerce")
        numeric[name] = values
        finite = values.map(
            lambda value: pd.notna(value) and math.isfinite(float(value))
        )
        in_range = values.ge(0).fillna(False)
        if name == "rating":
            in_range &= values.le(5).fillna(False)
        elif name == "discount_percentage":
            in_range &= values.le(100).fillna(False)
        elif name == "rating_count":
            in_range &= values.mod(1).eq(0).fillna(False)
        invalid = data[name].notna() & ~(finite & in_range)
        check(name + "_valid", invalid.sum())
        check(name + "_missing", data[name].isna().sum(), "warning")

    if {"actual_price", "discounted_price"} <= set(numeric):
        actual = numeric["actual_price"]
        discounted = numeric["discounted_price"]
        invalid = actual.notna() & discounted.notna() & discounted.gt(actual)
        check("discounted_price_not_above_actual", invalid.fillna(False).sum())

    errors = sum(not item["passed"] and item["severity"] == "error"
                 for item in checks)
    warnings = sum(not item["passed"] and item["severity"] == "warning"
                   for item in checks)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rows_checked": len(data),
        "status": "failed" if errors else "passed",
        "failed_checks": errors,
        "warning_checks": warnings,
        "missing_columns": sorted(missing),
        "checks": checks,
    }


def save_quality_report(report: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def require_quality(report: dict) -> None:
    if report["status"] != "passed":
        failed = [
            item["name"] for item in report["checks"]
            if not item["passed"] and item["severity"] == "error"
        ]
        raise ValueError("Data quality failed: " + ", ".join(failed))
