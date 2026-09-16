"""Exercise a running API without credentials or model downloads."""

import argparse

import httpx


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args(argv)
    with httpx.Client(base_url=args.url, timeout=30, trust_env=False) as client:
        for path in ("/health", "/ready", "/products", "/monitoring", "/metrics"):
            response = client.get(path)
            response.raise_for_status()
        first = client.get("/products", params={"limit": 1}).json()["products"][0]
        hits = client.get("/search", params={"q": first["product_id"]}).json()[
            "results"
        ]
        assert hits[0]["product_id"] == first["product_id"]
        prediction = client.post(
            "/predict", json={"product_name": first["product_name"]}
        )
        prediction.raise_for_status()
        assert prediction.json()["category"]
        result = client.post("/ask", json={"question": first["product_id"]}).json()
        assert first["product_id"] in result["source_ids"]
    print(
        "API smoke passed: readiness, catalog, search, prediction, evidence, monitoring."
    )


if __name__ == "__main__":
    main()
