"""Idempotent administrative catalog upgrade for existing SQLite TEST databases."""
import argparse
from pathlib import Path
import sqlite3

SQL_PATH = Path(__file__).parent / "database/sqlite/012_admin_units.sql"


def migrate(con):
    con.execute("SAVEPOINT admin_units_upgrade")
    try:
        for statement in SQL_PATH.read_text(encoding="utf-8").split(";"):
            if statement.strip():
                con.execute(statement)
        con.execute("RELEASE SAVEPOINT admin_units_upgrade")
    except Exception:
        con.execute("ROLLBACK TO SAVEPOINT admin_units_upgrade")
        con.execute("RELEASE SAVEPOINT admin_units_upgrade")
        raise
    return "Administrative catalog ready; existing units and business data preserved."


def main():
    parser = argparse.ArgumentParser(description="Nang cap danh muc hanh chinh tren database TEST.")
    parser.add_argument("--db", required=True)
    args = parser.parse_args()
    path = Path(args.db).resolve(strict=True)
    production = Path(__file__).resolve().with_name("salt_management.db")
    if (path == production or (production.exists() and path.samefile(production))
            or not path.name.upper().endswith("_TEST.DB")):
        parser.error("Chi chap nhan database *_TEST.db; khong migration database chinh.")
    con = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True)
    con.execute("PRAGMA foreign_keys=ON")
    try:
        print(migrate(con))
        con.commit()
    finally:
        con.close()


if __name__ == "__main__":
    main()
