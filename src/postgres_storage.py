"""Transactional PostgreSQL storage; connection details stay out of errors."""
import os
from contextlib import contextmanager
from pathlib import Path

import psycopg
from dotenv import dotenv_values

from src.load_to_db import DATABASE_COLUMNS, create_records, validate_columns

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def connect(read_only=False):
    settings = {**dotenv_values(ROOT / '.env'), **os.environ}
    url = settings.get('DATABASE_URL')
    kwargs = {} if url else {
        'host': settings.get('PGHOST', 'localhost'),
        'port': settings.get('PGPORT', '5432'),
        'dbname': settings.get('POSTGRES_DB', 'products'),
        'user': settings.get('POSTGRES_USER', 'products_app'),
        'password': settings.get('POSTGRES_PASSWORD'),
    }
    if not url and not kwargs['password']:
        raise ValueError('Set POSTGRES_PASSWORD in .env or DATABASE_URL in the environment.')
    try:
        with psycopg.connect(url or '', connect_timeout=10, **kwargs) as connection:
            if read_only:
                connection.execute('SET TRANSACTION READ ONLY')
            yield connection
    except psycopg.Error as error:
        raise RuntimeError(f'PostgreSQL operation failed (SQLSTATE {error.sqlstate or "connection"}).') from None


def load_database(data):
    validate_columns(data)
    data = data[DATABASE_COLUMNS].copy()
    if data.empty:
        raise ValueError('Cannot load an empty batch.')
    for name in ('product_id', 'product_name'):
        values = data[name].astype('string').str.strip()
        if (values.isna() | values.eq('')).any():
            raise ValueError(f'Missing or blank {name}.')
        data[name] = values
    if data.product_id.duplicated().any():
        raise ValueError('Duplicate product IDs in prepared batch.')
    columns = ', '.join(DATABASE_COLUMNS)
    placeholders = ', '.join(['%s'] * len(DATABASE_COLUMNS))
    updates = ', '.join(f'{c}=excluded.{c}' for c in DATABASE_COLUMNS if c != 'product_id')
    records = create_records(data)
    with connect() as connection:
        connection.execute((ROOT / 'sql/postgres/schema.sql').read_text())
        connection.execute((ROOT / 'sql/postgres/views.sql').read_text())
        connection.execute('CREATE TEMP TABLE batch_products (LIKE products) ON COMMIT DROP')
        with connection.cursor() as cursor:
            cursor.executemany(f'INSERT INTO batch_products ({columns}) VALUES ({placeholders})', records)
            cursor.executemany(f'INSERT INTO products ({columns}) VALUES ({placeholders}) ON CONFLICT(product_id) DO UPDATE SET {updates}', records)
        matches = ' AND '.join(f'p.{c} IS NOT DISTINCT FROM b.{c}' for c in DATABASE_COLUMNS)
        count = connection.execute(f'SELECT COUNT(*) FROM batch_products b JOIN products p ON p.product_id=b.product_id WHERE {matches}').fetchone()[0]
        if count != len(records):
            raise ValueError('Stored values do not match the incoming batch.')
    return count


def get_database_count():
    with connect(read_only=True) as connection:
        return connection.execute('SELECT COUNT(*) FROM products').fetchone()[0]
