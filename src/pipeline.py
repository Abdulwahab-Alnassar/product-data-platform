"""Extract, transform, validate, and upsert products with one command."""

import argparse
import logging
from pathlib import Path
from time import perf_counter
from typing import Optional

from src import clean_data as cleaning
from src import load_to_db as database
from src.logging_utils import pipeline_logging
from src.validate_data import build_quality_report, require_quality, save_quality_report

LOGGER = logging.getLogger("product_data_platform")
LOG_PATH = cleaning.PROJECT_ROOT / "logs" / "pipeline.log"


def run_pipeline(
    raw_data_path: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    backend: str = 'sqlite',
) -> dict[str, int]:
    """Validate before writing data; verify the batch separately from the total."""
    started = perf_counter()
    if backend not in ('sqlite', 'postgres'):
        raise ValueError('Unknown backend.')
    source = cleaning.RAW_DATA_PATH if raw_data_path is None else Path(raw_data_path)
    output = None if output_dir is None else Path(output_dir)
    cleaned_path = cleaning.PROCESSED_DATA_PATH if output is None else output / "cleaned_products.csv"
    sample_path = cleaning.SAMPLE_DATA_PATH if output is None else output / "cleaned_products_sample.csv"
    db_path = database.DATABASE_PATH if output is None else output / "products.db"
    report_path = cleaned_path.parent / "quality_report.json"

    try:
        LOGGER.info("[1/5] Extract: reading %s", source)
        raw = cleaning.load_data(source)
        if raw.empty:
            raise ValueError("The raw dataset contains no rows.")

        LOGGER.info("[2/5] Transform: cleaning %s rows", len(raw))
        cleaned = cleaning.clean_data(raw)
        database.validate_columns(cleaned)
        if cleaned.empty:
            raise ValueError("No usable products remain after cleaning.")

        LOGGER.info("[3/5] Validate: preparing unique products")
        prepared = database.prepare_data(cleaned)
        report = build_quality_report(prepared, source_columns=cleaned.columns)
        save_quality_report(report, report_path)
        LOGGER.info("Quality report: %s (errors=%s, warnings=%s)",
                    report_path, report["failed_checks"], report["warning_checks"])
        if report["warning_checks"]:
            LOGGER.warning("Missing numeric values: see quality report for counts")
        require_quality(report)

        LOGGER.info("[4/5] Save: writing cleaned CSV and sample")
        cleaning.save_data(
            cleaned, processed_path=cleaned_path, sample_path=sample_path
        )
        LOGGER.info("[5/5] Load: upserting %s products", len(prepared))
        if backend == 'postgres':
            from src import postgres_storage
            verified = postgres_storage.load_database(prepared)
        else:
            verified = database.load_database(prepared, database_path=db_path)
        if verified != len(prepared):
            raise ValueError(
                f"Database row count mismatch: expected {len(prepared)}, found {verified}."
            )

        total = postgres_storage.get_database_count() if backend == 'postgres' else database.get_database_count(db_path)
        summary = {
            "raw_rows": len(raw),
            "cleaned_rows": len(cleaned),
            "removed_rows": len(raw) - len(cleaned),
            "duplicate_product_ids": len(cleaned) - len(prepared),
            "batch_rows": verified,
            "database_rows": total,
        }
        LOGGER.info("Completed in %.3f seconds: %s", perf_counter() - started, summary)
        return summary
    except Exception:
        LOGGER.exception("Pipeline failed after %.3f seconds", perf_counter() - started)
        raise


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Raw CSV (default: data/raw/amazon.csv)")
    parser.add_argument("--output-dir", type=Path, help="Isolated output directory for demos")
    parser.add_argument('--backend', choices=['sqlite', 'postgres'], default='sqlite')
    args = parser.parse_args(argv)
    log_path = LOG_PATH if args.output_dir is None else args.output_dir / "pipeline.log"
    with pipeline_logging(log_path) as logger:
        summary = run_pipeline(args.input, args.output_dir, backend=args.backend)
        logger.info("Pipeline completed successfully.")
        logger.info("Database validation passed.")
        logger.info("Rows read: %s", summary["raw_rows"])
        logger.info("Rows after cleaning: %s", summary["cleaned_rows"])
        logger.info("Rows removed during cleaning: %s", summary["removed_rows"])
        logger.info("Duplicate product IDs: %s", summary["duplicate_product_ids"])
        logger.info("Verified batch products: %s", summary["batch_rows"])
        logger.info("Total products in database: %s", summary["database_rows"])


if __name__ == "__main__":
    main()
