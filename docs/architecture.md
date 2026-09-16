# Architecture and contracts

## Ownership of data

The CSV pipeline is the batch writer. It cleans source values, checks required
columns, chooses one row per product ID (highest rating count, first row for
ties), and checks the prepared batch before saving product outputs. Missing
numeric values are warnings; impossible ranges and inverted prices block loading.
Malformed source values can become missing during cleaning, so quality results
describe the cleaned batch, not every original source defect.

Products are keyed by `product_id`. Batch upserts preserve absent IDs and replace
all incoming values, including NULL. Every stored batch value is compared with a
temporary table before commit. CSV files and the database are not a distributed
transaction. Run one importer per output directory.

## Change tracking

The additive `changes.sql` schema adds inventory, event bookkeeping, a revision
row, and a change log. Rerunning the updated pipeline installs it on an existing
database without dropping products. Back up existing databases first.

Triggers write revision and change records inside the product transaction. SQLite
serializes writers. PostgreSQL increments a locked singleton row rather than using
a standalone sequence: this avoids a polling consumer advancing past a revision
whose transaction has not committed. PostgreSQL batch and event writers acquire
that row before modifying products to use a consistent lock order.

Search checks the committed revision before reusing its index. A replacement
index is built from one consistent catalog snapshot and swapped under a lock.
Concurrent queries may see the preceding committed snapshot; a request started
after a completed update refreshes on the new revision. There is no background
latency guarantee. Both change records and event receipts currently grow without
automatic retention; pruning requires a policy for consumer cursors and retries.

## Event contract

`ProductEvent` in `src/events.py` is the authoritative input schema. Payloads use
validated numbers, not currency strings. Unknown fields, nonfinite values,
negative stock, blank names, and unsupported operations are rejected.

- Same event ID and same payload: duplicate, no writes.
- Same event ID and different payload: conflict, no writes.
- Lower/equal source version under a new event ID: record as stale, no product change.
- Higher version: apply full product replacement or deletion, store version and receipt.
- Omitted stock: preserve inventory; explicit null: unknown; zero: out of stock.
- Delete: cascade inventory deletion and retain the source-version tombstone.

Data, inventory, receipt, version, and change log commit together. JSONL ingestion
is a sequence of individual transactions; it is not file-wide atomic. Event versions
must be assigned by the source. Do not mix ongoing versioned events with baseline
batch replacement unless the source ordering policy explicitly permits it.

## Read surfaces

The public catalog allowlist excludes reviews, review identifiers, customer names,
and customer IDs. Obvious contacts are masked in text. Search uses only the product
name, category, and description. Inventory is separate and unknown for original
sample rows. Demo event stock is synthetic, never inferred from an Amazon rating.

SQLite uses read-only URI connections. PostgreSQL read operations use read-only,
repeatable-read transactions. The shared local database account remains powerful;
the transaction setting is not a replacement for separate production roles.

## Model and API

Classification is independent of retrieval. Training receives names/labels and
produces a plain JSON artifact. Predictions never rewrite stored categories.
The API loads the configured model for each prediction, allowing a reviewed
artifact path to be switched after restart. Search state is process-local;
multiple workers would each maintain their own index and counters.

| Endpoint | Purpose |
| --- | --- |
| GET `/health`, `/ready` | Process and database checks |
| GET `/products`, `/products/{id}` | Paginated catalog and exact ID lookup |
| GET `/search` | Query, category, price cap, stock filter |
| POST `/predict` | Name-to-category inference |
| POST `/ask` | Facts or optional Ollama generation |
| POST `/events` | API-key guarded mutation |
| GET `/changes` | Cursor-based change feed |
| GET `/monitoring`, `/metrics` | Data-health report and process counters |

The OpenAPI schema at `/docs` documents exact parameters. Validation responses do
not echo submitted values. API access logging is disabled in the recommended
commands because query strings may contain user text.
