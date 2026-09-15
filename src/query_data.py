"""Read-only analytics and spreadsheet-safe exports."""
import sqlite3
from contextlib import closing
from pathlib import Path
import pandas as pd
from src.load_to_db import DATABASE_PATH


def load_analytics(backend='sqlite', database_path=None):
    if backend == 'postgres':
        from src.postgres_storage import connect
        with connect(read_only=True) as connection:
            cursor = connection.execute('SELECT * FROM product_analytics ORDER BY product_id')
            data = pd.DataFrame(cursor.fetchall(), columns=[c.name for c in cursor.description])
    elif backend == 'sqlite':
        path = Path(database_path or DATABASE_PATH).resolve()
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as connection:
            data = pd.read_sql_query('SELECT * FROM product_analytics ORDER BY product_id', connection)
    else:
        raise ValueError('Unknown backend.')
    for name in ('actual_price', 'discounted_price', 'discount_percentage', 'savings_inr', 'rating', 'rating_count'):
        data[name] = pd.to_numeric(data[name], errors='coerce')
    return data


def filter_products(data, search='', categories=None, min_rating=0, include_unrated=True):
    mask = (data.product_name.str.contains(search, case=False, regex=False, na=False)
            | data.product_id.str.contains(search, case=False, regex=False, na=False))
    if categories:
        mask &= data.main_category.isin(categories)
    mask &= data.rating.ge(min_rating) | (data.rating.isna() & include_unrated)
    return data.loc[mask].copy()


def export_csv(data):
    def safe(value):
        if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
            return "'" + value
        return value
    return data.map(safe).to_csv(index=False).encode('utf-8-sig')
