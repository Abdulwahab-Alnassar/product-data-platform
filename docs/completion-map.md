# Completion map

This map records repository deliverables. Finishing code does not replace six
months of learning, interview practice, coursework, or career preparation.
Months 1–2 follow the discussed work; the remaining stages were specified when
completing this application.

| Month | Deliverable | Acceptance evidence |
| --- | --- | --- |
| 1 | Cleaning, validation, databases, SQL, initial UI | Original tests, sample pipeline, saved SQL in CI |
| 2 | Classifier, baseline, split manifest, saved artifact | Isolated IDs, duplicate titles, reproducibility, abstention, serving tests |
| 3 | API, request validation, guarded ingestion | Both backends test authentication, limits, updates, and retrieval |
| 4 | Hybrid retrieval, exact IDs, cited Q&A, optional local generation | Retrieval fixture, unknown stock, citation validation, protocol tests |
| 5 | Versioned events, tombstones, change tracking | Replay, stale events, rollback, delete/recreate, cursor pagination, index refresh |
| 6 | Monitoring, backups, deterministic setup, docs | Shift tests, SQLite restore, PostgreSQL restore, container API smoke |

The main demo is reproducible without a cloud account. Optional Ollama generation
requires a locally installed model. Its adapter is tested with controlled
responses, not a downloaded model. The full local Kaggle file was not available
for this verification run; importing it remains an explicit user action.

Not claimed: real store inventory, a live Amazon feed, public production hosting,
Kafka/Debezium/Qdrant/Feast integrations, a latency SLA, or completed career tasks.
This repository uses smaller local components and identifies them accurately.
