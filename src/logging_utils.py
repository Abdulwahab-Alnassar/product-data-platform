"""Console and rotating-file logging, scoped to one pipeline execution."""

import logging
import sys
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGGER_NAME = "product_data_platform"


@contextmanager
def pipeline_logging(log_path: Path):
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(LOGGER_NAME)
    old_level, old_propagate = logger.level, logger.propagate
    file_handler = RotatingFileHandler(
        log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    console_handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    handlers = (file_handler, console_handler)
    for handler in handlers:
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        yield logger
    finally:
        for handler in handlers:
            logger.removeHandler(handler)
            handler.close()
        logger.setLevel(old_level)
        logger.propagate = old_propagate
