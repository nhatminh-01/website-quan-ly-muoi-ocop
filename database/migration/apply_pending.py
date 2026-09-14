"""Apply repository PostgreSQL migrations that are not recorded yet.

This is intentionally conservative: it only runs numbered application SQL
migrations (004+), and refuses to bootstrap a database that has no
``app.schema_migrations`` table.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend_db import load_settings


VERSION_RE = re.compile(r"schema_migrations\s*\(version\)[^;]*?VALUES\s*\(\s*'([^']+)'", re.I | re.S)


def main() -> int:
    root = ROOT / "database"
    sql_dir = root / "sql"
    settings = load_settings()
    with psycopg.connect(
        host=settings.host, port=settings.port, dbname=settings.dbname,
        user=settings.user, password=settings.password, autocommit=True,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('app.schema_migrations')")
            if cur.fetchone()[0] is None:
                print("Chua co app.schema_migrations; hay khoi tao database theo database\\README.md.")
                return 2
            cur.execute("SELECT version FROM app.schema_migrations")
            applied = {str(row[0]) for row in cur.fetchall()}
            for path in sorted(sql_dir.glob("[0-9][0-9][0-9]_*.sql")):
                if path.name[:3] < "004":
                    continue
                sql = path.read_text(encoding="utf-8")
                versions = set(VERSION_RE.findall(sql))
                if versions and versions.issubset(applied):
                    continue
                print(f"Dang ap dung {path.name} ...")
                cur.execute(sql)
                applied.update(versions)
    print("Migration: da san sang.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
