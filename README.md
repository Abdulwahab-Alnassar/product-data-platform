# Product Data Platform

A personal data engineering and AI project for building a reliable platform that processes, validates, stores, and retrieves product data.

## Project Goal

The goal of this project is to build an end-to-end product data platform, starting with batch data processing and gradually extending it to real-time data pipelines and AI-powered product question answering.

## Planned Features

- Product data ingestion
- Data validation and cleaning
- Relational database storage
- SQL-based analysis
- Automated testing
- Real-time data pipelines
- Hybrid search and RAG
- Data privacy and governance

## Technology Stack

- Python
- Pandas
- SQLite (current storage)
- PostgreSQL (planned)
- SQL
- Pytest
- Git and GitHub

Additional technologies will be introduced gradually as the project develops.

## Current Progress

- [x] Project structure initialized
- [x] Dataset exploration
- [x] Data cleaning pipeline
- [x] Database integration
- [x] SQL analysis
- [x] Automated testing
- [x] Unified ETL pipeline (week 2, day 1)

## Running the ETL Pipeline

Run these commands from the repository root, with your Python virtual
environment activated:

```bash
python -m pip install -r requirements.txt
python -m src.pipeline
```

Before running, place the original Amazon Sales Dataset at
`data/raw/amazon.csv`. The full raw dataset is local and is not included
in the repository. The pipeline reports an error if this file is missing;
it does not substitute the public sample for the full dataset.

The pipeline reuses the existing functions in `src/clean_data.py` and
`src/load_to_db.py`:

1. **Extract:** read the raw CSV.
2. **Transform:** clean text and numeric values, remove identical rows
   and rows with missing product IDs or names, and remove the
   `user_id` and `user_name` columns.
3. **Validate and prepare:** require the database columns and select one
   row per product ID, keeping the row with the highest rating count.
4. **Save:** write the cleaned CSV and its first 100 rows as a public sample.
5. **Load and verify:** load the prepared products into SQLite and compare
   the inserted row count with the prepared row count.

| Output | Location |
| --- | --- |
| Cleaned data, before deduplication by product ID | `data/processed/cleaned_products.csv` |
| First 100 cleaned rows, without user ID/name columns | `data/sample/cleaned_products_sample.csv` |
| SQLite database with one row per product ID | `data/processed/products.db` |

The final summary reports raw rows, cleaned rows, rows removed during
cleaning, duplicate product IDs removed before loading, and database rows.
The cleaned CSV can contain more rows than the database because different
rows may refer to the same product.

The loader currently refreshes the contents of the `products` table on
each successful run; it does not yet perform incremental updates.
The pipeline rejects empty input, missing required columns, and data with
no usable products before writing outputs. Other failures raise an error;
a success summary is printed only after the row-count check passes.
Saving CSV files and loading SQLite are separate operations, not one
transaction across all outputs.

The existing standalone commands still work:

```bash
python src/clean_data.py
python src/load_to_db.py
```

## Running Tests

Install the project dependencies:

```bash
python -m pip install -r requirements.txt
```

Run the automated test suite:

```bash
python -m pytest -v
```

Pipeline tests use small synthetic CSVs and temporary SQLite databases;
they do not require Kaggle data or write to your project's data files.

## Dataset

This project uses the public Amazon Sales Dataset available on Kaggle.

## Author

Abdulwahab Alnassar  
Computer Science Student at King Saud University
