"""Create or restore a SQLite backup without overwriting an existing file."""

import argparse
import sqlite3
from contextlib import closing
from pathlib import Path


def copy_database(source, destination):
    source, destination = Path(source), Path(destination)
    if not source.is_file():
        raise FileNotFoundError("Source database does not exist.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents accidentally replacing the working database.
    with destination.open("xb"):
        pass
    try:
        with closing(
            sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)
        ) as src:
            with closing(sqlite3.connect(destination)) as dst:
                src.backup(dst)
                if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Backup did not pass SQLite integrity checking.")
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args(argv)
    copy_database(args.source, args.destination)
    print(f"Verified copy saved to {args.destination}")


if __name__ == "__main__":
    main()
