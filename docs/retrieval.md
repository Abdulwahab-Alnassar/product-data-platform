# Retrieval and product Q&A

## Local search

TF-IDF word/bigram similarity contributes 70% of the score. A rank-limited SVD
projection of the same corpus contributes 30% cosine similarity when enough rows
and features exist. Tiny catalogs fall back to lexical retrieval. These latent
vectors are lightweight corpus-specific representations, not pretrained semantic
embeddings. Unknown vocabulary may produce no results.

Exact product-code tokens receive priority. Category, price-cap, and in-stock
filters apply before truncating results. Missing prices do not pass a price cap;
unknown inventory does not pass the stock filter. Normal matches below 0.08 are
discarded. The thresholds/weights are demo choices, not optimized relevance claims.

`evaluation/search_cases.json` contains five explicit cases based on the public
sample. `python -m src.evaluate_search` reports hit rate and reciprocal rank.
This fixture checks basic retrieval behavior; it is too small and manually selected
to justify a general search-quality claim.

## Facts mode

The default answer returns product names, prices, ratings, inventory state, and
source IDs from one catalog snapshot. It does not invent warranty terms, live prices,
or stock. Missing evidence produces a clear no-match response. Product descriptions
are shown as supporting records, not treated as commands.

## Optional local generation

Install Ollama separately and download a model you are permitted to run. Configure
`OLLAMA_URL=http://127.0.0.1:11434` and `OLLAMA_MODEL` with the exact installed model
name, then restart the local API/dashboard. Select Ollama mode in Q&A or pass
`"mode": "ollama"` to `/ask`. No model is downloaded automatically by this project.

The adapter sends a bounded, redacted question and up to three catalog records to
`/api/generate`. No customer review fields enter the prompt, and the model receives
no tools or write access. The response must include valid retrieved source IDs.
Timeouts, missing configuration, and invalid response/citation formats fall back
to catalog facts. Citations are format/evidence-ID checks, not entailment checking:
a generated statement can still be wrong. The UI labels generated explanations.

This mode is available when running the app directly. Compose does not include an
Ollama server or automatically forward its settings; connect and configure your
own reachable local service explicitly if extending that setup. Do not use
container `localhost` to refer to a service on the host.

## Reference material

- [scikit-learn common pitfalls](https://scikit-learn.org/stable/common_pitfalls.html)
- [FastAPI testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [Ollama generation API](https://docs.ollama.com/api/generate)

The optional adapter is verified with controlled success/failure responses.
Generated-answer quality from an actual installed model was not evaluated here.
