"""Explicit, test-only entry point for the additive OCOP 1-2 migration."""
import argparse
from pathlib import Path
import sqlite3


def main():
    parser = argparse.ArgumentParser(description="Migration OCOP 1-2 tren database TEST.")
    parser.add_argument("--db", required=True)
    args = parser.parse_args()
    path = Path(args.db).resolve(strict=True)
    production = Path(__file__).resolve().with_name("salt_management.db")
    if path == production or (production.exists() and path.samefile(production)) or not path.name.upper().endswith("_TEST.DB"):
        parser.error("Chi chap nhan database *_TEST.db; khong migration database chinh.")
    from ocop_db import migrate
    con = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    try:
        result = migrate(con)
        con.commit()
        print(result)
    finally:
        con.close()


if __name__ == "__main__":
    main()
