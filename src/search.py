"""Lexical and latent-vector retrieval with exact product-code priority."""

import re
import threading

import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

from src.catalog import Catalog


class SearchIndex:
    def __init__(self, rows, revision=0):
        self.rows, self.revision = rows, revision
        self.vectorizer = None
        self.svd = None
        if not rows:
            return
        documents = [
            " ".join(
                str(row.get(key) or "")
                for key in ("product_name", "category", "about_product")
            )
            for row in rows
        ]
        self.vectorizer = TfidfVectorizer(
            strip_accents="unicode",
            stop_words="english",
            ngram_range=(1, 2),
            max_features=20000,
        )
        try:
            self.sparse = self.vectorizer.fit_transform(documents)
        except ValueError:
            self.vectorizer = None  # Exact IDs still work for an empty vocabulary.
            return
        size = min(64, self.sparse.shape[0] - 1, self.sparse.shape[1] - 1)
        if size >= 2:
            self.svd = TruncatedSVD(n_components=size, random_state=42)
            self.dense = normalize(self.svd.fit_transform(self.sparse))

    def search(self, query, limit=5, category=None, max_price=None, in_stock=False):
        if not query.strip() or len(query) > 1000 or not 1 <= limit <= 50:
            raise ValueError(
                "Provide a query of 1–1000 characters and a limit of 1–50."
            )
        if not self.rows:
            return []
        scores = np.zeros(len(self.rows))
        if self.vectorizer is not None:
            vector = self.vectorizer.transform([query])
            lexical = (self.sparse @ vector.T).toarray().ravel()
            scores = lexical
            if self.svd is not None and vector.nnz:
                latent = self.dense @ normalize(self.svd.transform(vector))[0]
                scores = 0.7 * lexical + 0.3 * np.maximum(latent, 0)
        tokens = {token.casefold() for token in re.findall(r"[\w-]+", query)}
        matches = []
        for index, row in enumerate(self.rows):
            if category and row["main_category"] != category:
                continue
            if max_price is not None and (
                row["discounted_price"] is None or row["discounted_price"] > max_price
            ):
                continue
            if in_stock and not (
                row.get("stock_quantity") is not None and row["stock_quantity"] > 0
            ):
                continue
            exact = row["product_id"].casefold() in tokens
            if exact or scores[index] >= 0.08:
                matches.append(
                    {
                        **row,
                        "score": round(float(scores[index]), 6),
                        "exact_match": exact,
                    }
                )
        matches.sort(
            key=lambda row: (-row["exact_match"], -row["score"], row["product_id"])
        )
        return matches[:limit]


class SearchService:
    def __init__(self, catalog=None):
        self.catalog = catalog or Catalog()
        self.index = None
        self.lock = threading.Lock()

    def current(self):
        with self.lock:
            revision = self.catalog.revision()
            if self.index is None or self.index.revision != revision:
                revision, rows = self.catalog.snapshot()
                self.index = SearchIndex(rows, revision)
            return self.index

    def search(self, *args, **kwargs):
        return self.current().search(*args, **kwargs)
