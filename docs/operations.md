# Operations and troubleshooting

## Existing project upgrade

1. Commit or save your local edits before `git pull --ff-only origin main`.
2. Install `requirements.lock` into your Python 3.12 environment.
3. Back up any database you want to retain.
4. Run the updated pipeline once to install the additive change-tracking schema.
5. Train the classifier, then start the dashboard and API.

Keep your original raw data at `data/raw/amazon.csv`. The unified sample command
is `python -m src.demo`. For your full local dataset:

```powershell
python -m src.demo --input data/raw/amazon.csv --output-dir data/processed/full --model-dir artifacts/full
$env:SQLITE_PATH = 'data/processed/full/products.db'
$env:MODEL_PATH = 'artifacts/full/model.json'
python -m streamlit run dashboard.py
```

Here `python` means the interpreter in your virtual environment. In PowerShell
you can use `.\.venv\Scripts\python.exe` directly without changing execution policy.
Each new terminal needs its environment variables, or place the settings in a
local `.env`. Process environment wins over `.env` for `Settings` and PostgreSQL.

## Configuration

| Setting | Default / behavior |
| --- | --- |
| `PLATFORM_BACKEND` | `sqlite`; `DASHBOARD_BACKEND` remains a compatibility fallback |
| `SQLITE_PATH` | `data/processed/products.db` under the project root |
| `MODEL_PATH` | `artifacts/category/model.json` |
| `DATABASE_URL` | Optional complete PostgreSQL connection string |
| `PGHOST`, `PGPORT` | `localhost`, `5432` outside Compose |
| `POSTGRES_USER`, `POSTGRES_DB` | `products_app`, `products` |
| `POSTGRES_PASSWORD` | Required when a complete URL is absent |
| `PLATFORM_API_KEY` | Empty disables `/events`; reads remain local and unauthenticated |
| `OLLAMA_URL`, `OLLAMA_MODEL` | Empty selects factual fallback; see retrieval guide |

The original pipeline CLI still selects its backend with `--backend` and its
output paths with `--output-dir`; it does not infer a storage choice from the UI.
PostgreSQL is internal to Compose, so use `docker compose exec` to inspect it.

## Events over HTTP

Set a long random `PLATFORM_API_KEY` in `.env` and restart the API. Use
`X-API-Key` for POST `/events`. Never put the key in a URL, README, or screenshot.
Interactive API docs show the full body schema. The CLI `python -m src.events
examples/events.jsonl` is a trusted local administration path and does not use
the HTTP key. It uses the same validation and transaction code.

## Full input in Docker

```powershell
docker compose run --rm -v "${PWD}/data/raw:/input:ro" pipeline python -m src.demo --backend postgres --input /input/amazon.csv --output-dir data/processed --model-dir artifacts/category
```

Run this after the database is healthy. This modifies the shared catalog and
model volume; do not use it as a harmless read-only preview. Input IDs missing
from the new batch are preserved. Use a separate Compose project for a separate
catalog. The initialization sample runs again when its container is recreated,
so manage baseline imports deliberately after switching to full data.

## Reports and troubleshooting

The pipeline writes `quality_report.json` and `run_report.json`. Match `run_id`
before using a quality result: a missing input can fail before a new quality
report exists. `run_report.json` records the latest attempted run and failure type.
Logs contain stage and failure details, so treat them as local operational data.

- **Missing change tables:** run the updated pipeline once against that database.
- **Model unavailable:** run `src.train_model` or `src.demo`, then check `MODEL_PATH`.
- **No stock-filter results:** original data has no inventory; unknown stock is excluded.
- **No vocabulary match:** the classifier abstains; try a representative product name.
- **PostgreSQL auth after changing `.env`:** the volume retains its original password.
  Changing the variable does not rotate the stored password. Use the original
  setting or rotate the database credential deliberately.
- **Port in use:** stop the old process or change the host port in Compose.
- **Pipeline Exited (0):** normal; the initialization job is finished.

## Backups and restoration

SQLite online backup (the destination must not already exist):

```powershell
python -m src.backup data/processed/demo/products.db backups/products.backup
python -m src.backup backups/products.backup data/processed/restored/products.db
```

The same command restores into a new file and verifies database integrity. Point
`SQLITE_PATH` to the restored file only after checking it. Do not overwrite your
working database to test restoration.

PostgreSQL backup, using the default configured role/database:

```powershell
docker compose exec db pg_dump -U products_app -d products -Fc -f /tmp/products.backup
docker compose cp db:/tmp/products.backup ./products.backup
```

Use a new database to verify restoration:

```powershell
docker compose exec db createdb -U products_app restore_check
docker compose exec db pg_restore -U products_app -d restore_check --exit-on-error /tmp/products.backup
docker compose exec db psql -U products_app -d restore_check -c "SELECT COUNT(*) FROM products;"
```

Change role/database names if you changed them in `.env`. These commands avoid
PowerShell binary redirection. Keep backups private. Model artifacts require a
separate directory backup or reproducible retraining with the original data hash.

## Monitoring and retraining

`python -m src.monitor` reports missing fields, unknown stock, vocabulary coverage,
and category total-variation distance against the training distribution. A distance
above 0.2 is a demo review threshold, not a statistical quality guarantee. No
automatic retraining or promotion occurs. Train into a new model directory, review
validation results and errors, and keep the old directory for rollback.

API counters are in-memory per process and reset on restart. For production use,
add an authenticated gateway, durable metrics/log collection, independent read
roles, migration management, and retention before exposing the service.
