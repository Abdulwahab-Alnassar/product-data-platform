"""Evaluate a small, explicit retrieval fixture; do not treat it as a benchmark."""

import argparse
import json
from pathlib import Path

from src.catalog import Catalog
from src.reports import write_json
from src.search import SearchService


def evaluate(search, cases, k=5):
    results = []
    for case in cases:
        hits = search.search(case["query"], limit=k)
        rank = next(
            (
                i + 1
                for i, row in enumerate(hits)
                if row["product_id"] in case["relevant_ids"]
            ),
            None,
        )
        results.append(
            {
                "query": case["query"],
                "rank": rank,
                "returned_ids": [row["product_id"] for row in hits],
            }
        )
    if not results:
        raise ValueError("Evaluation needs at least one query.")
    return {
        "queries": len(results),
        "k": k,
        "hit_rate_at_k": sum(row["rank"] is not None for row in results) / len(results),
        "mrr_at_k": sum(1 / row["rank"] if row["rank"] else 0 for row in results)
        / len(results),
        "cases": results,
        "limitation": "Small manually selected smoke fixture, not independent relevance evaluation.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases", type=Path, default=Path("evaluation/search_cases.json")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("artifacts/search_evaluation.json")
    )
    args = parser.parse_args(argv)
    result = evaluate(
        SearchService(Catalog()), json.loads(args.cases.read_text(encoding="utf-8"))
    )
    write_json(args.output, result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
