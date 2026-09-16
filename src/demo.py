"""Prepare the included sample, classifier, and monitoring report in one command."""

import argparse
import json
from pathlib import Path

from src.catalog import Catalog
from src.config import ROOT, Settings
from src.monitor import monitor
from src.pipeline import run_pipeline
from src.predict import CategoryModel
from src.reports import write_json
from src.train_model import train


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, default=ROOT / "data/sample/amazon_sample.csv"
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/processed/demo")
    parser.add_argument("--model-dir", type=Path, default=ROOT / "artifacts/category")
    parser.add_argument("--backend", choices=["sqlite", "postgres"], default="sqlite")
    args = parser.parse_args(argv)
    print(
        f"Using input: {args.input}. The included sample is a demonstration, not the full dataset."
    )
    summary = run_pipeline(args.input, args.output_dir, args.backend)
    report = train(args.output_dir / "cleaned_products.csv", args.model_dir)
    settings = Settings(
        backend=args.backend,
        database_path=args.output_dir / "products.db",
        model_path=args.model_dir / "model.json",
        report_dir=args.model_dir,
    )
    health = monitor(Catalog(settings), CategoryModel(settings.model_path))
    write_json(args.model_dir / "monitoring.json", health)
    print(
        json.dumps(
            {
                "pipeline": summary,
                "model_id": report["model_id"],
                "test": report["test"],
            },
            indent=2,
        )
    )
    print(f"Model: {settings.model_path}")
    if args.backend == "sqlite":
        print(
            f"Set SQLITE_PATH to {settings.database_path} when starting the dashboard or API."
        )


if __name__ == "__main__":
    main()
