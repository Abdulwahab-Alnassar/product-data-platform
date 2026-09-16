"""Describe catalog health and distribution changes without automatic retraining."""

import argparse
import json
from collections import Counter
from datetime import datetime, timezone

from src.catalog import Catalog
from src.config import Settings
from src.predict import CategoryModel
from src.reports import write_json


def monitor(catalog, model=None):
    revision, rows = catalog.snapshot()
    count = len(rows)
    categories = Counter(row["main_category"] for row in rows)
    distribution = (
        {label: value / count for label, value in categories.items()} if count else {}
    )
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "catalog_revision": revision,
        "products": count,
        "category_counts": dict(categories),
        "missing_price": sum(row["discounted_price"] is None for row in rows),
        "missing_rating": sum(row["rating"] is None for row in rows),
        "unknown_inventory": sum(row["stock_quantity"] is None for row in rows),
        "alerts": [],
    }
    if not rows:
        result["alerts"].append("Catalog is empty.")
    if model:
        baseline = model.data["training_distribution"]
        distance = (
            sum(
                abs(distribution.get(label, 0) - baseline.get(label, 0))
                for label in set(distribution) | set(baseline)
            )
            / 2
            if count
            else None
        )
        result["model_id"] = model.data["model_id"]
        result["category_total_variation"] = distance
        if count:
            features = model.vectorizer.transform([row["product_name"] for row in rows])
            result["unknown_vocabulary_fraction"] = float(
                (features.getnnz(axis=1) == 0).mean()
            )
        if distance is not None and distance > 0.2:
            result["alerts"].append(
                "Category mix changed by more than the demo threshold (0.2); review before retraining."
            )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="artifacts/monitoring.json")
    args = parser.parse_args(argv)
    settings = Settings.from_env()
    model = (
        CategoryModel(settings.model_path) if settings.model_path.is_file() else None
    )
    report = monitor(Catalog(settings), model)
    from pathlib import Path

    write_json(Path(args.output), report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
