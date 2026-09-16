"""Small-catalog storage and a transactional change feed for both databases."""

import math
import sqlite3
from contextlib import contextmanager, closing
from decimal import Decimal

from src.config import Settings
from src.privacy import redact


def public_value(value):
    if isinstance(value, Decimal):
        value = float(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


class Catalog:
    def __init__(self, settings=None):
        self.settings = settings or Settings.from_env()

    @contextmanager
    def connection(self, write=False):
        if self.settings.backend == "postgres":
            from src.postgres_storage import connect

            with connect(read_only=not write) as con:
                if not write:
                    # The revision and rows must belong to the same committed snapshot.
                    con.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                yield con
        else:
            path = self.settings.database_path.resolve()
            if not path.is_file():
                raise FileNotFoundError(
                    "Run the data pipeline before opening the catalog."
                )
            uri = path.as_uri() + ("?mode=rw" if write else "?mode=ro")
            with closing(sqlite3.connect(uri, uri=True, timeout=15)) as con:
                con.execute("PRAGMA foreign_keys=ON")
                con.execute("BEGIN IMMEDIATE" if write else "BEGIN")
                with con:
                    yield con

    def execute(self, con, statement, values=()):
        # SQL templates are internal constants; user data only goes in parameters.
        if self.settings.backend == "postgres":
            statement = statement.replace("?", "%s")
        return con.execute(statement, values)

    def revision(self):
        with self.connection() as con:
            return con.execute(
                "SELECT revision FROM catalog_state WHERE singleton=1"
            ).fetchone()[0]

    def snapshot(self):
        with self.connection() as con:
            revision = con.execute(
                "SELECT revision FROM catalog_state WHERE singleton=1"
            ).fetchone()[0]
            cursor = con.execute("""SELECT p.product_id, p.product_name, p.category,
                p.discounted_price, p.actual_price, p.rating, p.rating_count,
                p.about_product, i.stock_quantity
                FROM products p LEFT JOIN inventory i ON i.product_id=p.product_id
                ORDER BY p.product_id LIMIT 50001""")
            names = [column[0] for column in cursor.description]
            rows = [
                dict(zip(names, map(public_value, row))) for row in cursor.fetchall()
            ]
        if len(rows) > 50000:
            raise ValueError("This in-memory demo supports at most 50,000 products.")
        for row in rows:
            for name in ("product_name", "about_product", "category"):
                row[name] = redact(row[name])
            row["main_category"] = (
                row["category"].split("|")[0].strip() or "Uncategorized"
            )
        return revision, rows

    def changes(self, after=0, limit=100):
        if after < 0 or not 1 <= limit <= 500:
            raise ValueError("Invalid change-feed cursor or limit.")
        with self.connection() as con:
            rows = self.execute(
                con,
                """SELECT change_id, product_id, operation, changed_at
                FROM catalog_changes WHERE change_id > ? ORDER BY change_id LIMIT ?""",
                (after, limit),
            ).fetchall()
        return [
            dict(zip(("change_id", "product_id", "operation", "changed_at"), row))
            for row in rows
        ]
