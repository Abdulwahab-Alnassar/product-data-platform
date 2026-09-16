"""Train a category classifier and publish an auditable, executable-free artifact."""

import argparse
import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.dummy import DummyClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)
from sklearn.pipeline import Pipeline

from src.config import ROOT
from src.privacy import redact
from src.reports import write_json


def prepare_training_data(data):
    required = {"product_id", "product_name", "category"}
    if not required <= set(data.columns):
        raise ValueError("Training requires product_id, product_name, and category.")
    frame = data[list(sorted(required))].dropna().copy()
    for column in required:
        frame[column] = frame[column].astype(str).str.strip()
    frame = frame.loc[frame[list(required)].ne("").all(axis=1)]
    frame["label"] = frame.category.str.split("|").str[0].str.strip()
    frame = frame.loc[frame.label.ne("")].copy()
    frame["product_name"] = frame.product_name.map(redact)
    frame["name_key"] = frame.product_name.str.casefold().str.replace(
        r"\s+", " ", regex=True
    )
    # The same product or identical title must not appear on both sides of a split.
    frame = (
        frame.sort_values("product_id")
        .drop_duplicates("product_id")
        .drop_duplicates("name_key")
    )
    counts = frame.label.value_counts()
    excluded = counts[counts < 5].to_dict()
    frame = frame.loc[frame.label.isin(counts[counts >= 5].index)].copy()
    if frame.label.nunique() < 2:
        raise ValueError(
            "Need at least two categories with five distinct product names each."
        )
    return frame.reset_index(drop=True), {str(k): int(v) for k, v in excluded.items()}


def split_data(frame, seed):
    rng = np.random.default_rng(seed)
    train, validation, test = [], [], []
    for _, group in frame.groupby("label", sort=True):
        indexes = rng.permutation(group.index).tolist()
        holdout = max(1, int(len(indexes) * 0.2))
        test.extend(indexes[:holdout])
        validation.extend(indexes[holdout : 2 * holdout])
        train.extend(indexes[2 * holdout :])
    return frame.loc[train], frame.loc[validation], frame.loc[test]


def metrics(truth, predicted):
    return {
        "accuracy": float(accuracy_score(truth, predicted)),
        "macro_f1": float(f1_score(truth, predicted, average="macro", zero_division=0)),
    }


def train(input_path, output_dir, seed=42):
    frame, excluded = prepare_training_data(pd.read_csv(input_path))
    training, validation, testing = split_data(frame, seed)
    candidates = []
    fitted = []
    for strength in (0.5, 2.0):
        model = Pipeline(
            [
                (
                    "text",
                    TfidfVectorizer(
                        ngram_range=(1, 2), strip_accents="unicode", max_features=20000
                    ),
                ),
                (
                    "classifier",
                    LogisticRegression(
                        C=strength,
                        class_weight="balanced",
                        max_iter=1000,
                        random_state=seed,
                    ),
                ),
            ]
        )
        model.fit(training.product_name, training.label)
        score = metrics(validation.label, model.predict(validation.product_name))
        fitted.append(model)
        candidates.append({"C": strength, **score})
    best = max(range(len(candidates)), key=lambda index: candidates[index]["macro_f1"])
    model = fitted[best]
    # Keep the selected training-only model: the reported test score describes exactly this artifact.
    predicted = model.predict(testing.product_name)
    baseline = DummyClassifier(strategy="most_frequent").fit(
        training.product_name, training.label
    )
    vectorizer, classifier = model.named_steps["text"], model.named_steps["classifier"]
    fingerprint = hashlib.sha256(
        frame[["product_id", "product_name", "label"]].to_csv(index=False).encode()
    ).hexdigest()
    identity = {
        "data": fingerprint,
        "seed": seed,
        "sklearn": sklearn.__version__,
        "coef": classifier.coef_.tolist(),
        "idf": vectorizer.idf_.tolist(),
        "intercept": classifier.intercept_.tolist(),
        "classes": classifier.classes_.tolist(),
    }
    model_id = hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()
    ).hexdigest()[:16]
    artifact = {
        "format_version": 1,
        "model_id": model_id,
        "data_sha256": fingerprint,
        "sklearn_version": sklearn.__version__,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "vocabulary": {
            key: int(value) for key, value in vectorizer.vocabulary_.items()
        },
        "idf": vectorizer.idf_.tolist(),
        "classes": classifier.classes_.tolist(),
        "coef": classifier.coef_.tolist(),
        "intercept": classifier.intercept_.tolist(),
        "training_distribution": (
            training.label.value_counts(normalize=True)
        ).to_dict(),
    }
    report = {
        "model_id": model_id,
        "data_sha256": fingerprint,
        "seed": seed,
        "python": platform.python_version(),
        "sklearn": sklearn.__version__,
        "rows": len(frame),
        "excluded_rare_categories": excluded,
        "split_sizes": {
            "train": len(training),
            "validation": len(validation),
            "test": len(testing),
        },
        "split_product_ids": {
            name: part.product_id.tolist()
            for name, part in [
                ("train", training),
                ("validation", validation),
                ("test", testing),
            ]
        },
        "validation_candidates": candidates,
        "chosen_C": candidates[best]["C"],
        "test": metrics(testing.label, predicted),
        "baseline_test": metrics(testing.label, baseline.predict(testing.product_name)),
        "classification_report": classification_report(
            testing.label, predicted, zero_division=0, output_dict=True
        ),
        "confusion_matrix": confusion_matrix(
            testing.label, predicted, labels=classifier.classes_
        ).tolist(),
        "class_order": classifier.classes_.tolist(),
        "test_errors": [
            {
                "product_id": row.product_id,
                "expected": row.label,
                "predicted": str(guess),
            }
            for (_, row), guess in zip(testing.iterrows(), predicted)
            if row.label != guess
        ],
        "limitations": [
            "Small catalog snapshot; not an estimate of real-world accuracy.",
            "Identical titles are deduplicated; similar product families may still cross splits.",
            "Only the product name is used; probabilities are not calibrated confidence.",
        ],
    }
    output_dir = Path(output_dir)
    write_json(output_dir / "evaluation.json", report)
    write_json(output_dir / "model.json", artifact)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, default=ROOT / "data/processed/cleaned_products.csv"
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts/category")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    report = train(args.input, args.output_dir, args.seed)
    print(
        json.dumps(
            {
                key: report[key]
                for key in ("model_id", "split_sizes", "test", "baseline_test")
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
