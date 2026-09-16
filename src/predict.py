"""Read plain JSON model weights instead of loading executable pickle files."""

import json
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from scipy.special import expit, softmax

from src.privacy import redact


class CategoryModel:
    def __init__(self, path):
        path = Path(path)
        if path.stat().st_size > 20_000_000:
            raise ValueError("Model artifact exceeds the supported size.")
        self.data = json.loads(path.read_text(encoding="utf-8"))
        if self.data.get("format_version") != 1:
            raise ValueError("Unsupported model format; retrain the classifier.")
        self.classes = self.data["classes"]
        if len(self.classes) < 2 or len(set(self.classes)) != len(self.classes):
            raise ValueError("A classifier needs at least two distinct classes.")
        self.coef = np.asarray(self.data["coef"], dtype=float)
        self.intercept = np.asarray(self.data["intercept"], dtype=float)
        self.vectorizer = TfidfVectorizer(
            vocabulary=self.data["vocabulary"],
            ngram_range=(1, 2),
            strip_accents="unicode",
        )
        self.vectorizer.idf_ = np.asarray(self.data["idf"], dtype=float)
        if (
            set(self.data["vocabulary"].values())
            != set(range(len(self.data["vocabulary"])))
            or self.vectorizer.idf_.shape != (len(self.data["vocabulary"]),)
            or not np.isfinite(self.vectorizer.idf_).all()
        ):
            raise ValueError("Invalid vectorizer weights or vocabulary.")
        expected_rows = 1 if len(self.classes) == 2 else len(self.classes)
        if self.coef.shape != (
            expected_rows,
            len(self.data["vocabulary"]),
        ) or self.intercept.shape != (expected_rows,):
            raise ValueError("Invalid model dimensions.")
        if not np.isfinite(self.coef).all() or not np.isfinite(self.intercept).all():
            raise ValueError("Invalid model weights.")

    def predict(self, name):
        if not name.strip() or len(name) > 2000:
            raise ValueError("Product name must contain 1–2000 characters.")
        features = self.vectorizer.transform([redact(name)])
        if not features.nnz:
            return {
                "category": None,
                "abstained": True,
                "reason": "No known vocabulary in this name.",
                "model_id": self.data["model_id"],
            }
        logits = np.asarray(features @ self.coef.T).ravel() + self.intercept
        probabilities = (
            np.array([1 - expit(logits[0]), expit(logits[0])])
            if len(self.classes) == 2
            else softmax(logits)
        )
        best = int(np.argmax(probabilities))
        return {
            "category": self.classes[best],
            "abstained": False,
            "model_id": self.data["model_id"],
            "probability": round(float(probabilities[best]), 6),
            "probabilities": {
                label: round(float(value), 6)
                for label, value in zip(self.classes, probabilities)
            },
        }
