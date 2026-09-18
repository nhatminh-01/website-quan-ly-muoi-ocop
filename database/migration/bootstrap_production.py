"""Bootstrap a brand-new PTNT production database from repository SQL.

This command is intentionally conservative: it never drops or truncates data
and refuses to run when any application table already exists in the target
schemas.  It is used once for the empty ``ocop_db`` database; subsequent
changes are handled by ``apply_pending.py``.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend_db import load_settings


def _target_is_empty(conn) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_schema, COUNT(*)::INTEGER
            FROM information_schema.tables
            WHERE table_schema IN ('qd5277', 'qd5333', 'app', 'staging')
              AND table_type='BASE TABLE'
            GROUP BY table_schema
            HAVING COUNT(*) > 0
            ORDER BY table_schema
            """
        )
        found = cur.fetchall()
    if found:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('app.schema_migrations')")
            initialized = cur.fetchone()[0] is not None
        if initialized:
            # A normal restart may call this helper again.  Existing
            # migrations are handled by apply_pending.py; do not replay them.
            return False
        details = ", ".join(f"{schema}={count}" for schema, count in found)
        raise RuntimeError(
            "Production target khong rong (" + details + "). "
            "Khong tu dong ghi de; dung backup/duyet rieng truoc khi migrate."
        )
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file",
        default=str(ROOT / "database" / ".env.production"),
        help="Path to the production env file (default: database/.env.production)",
    )
    args = parser.parse_args()
    settings = load_settings(args.env_file)

    migration_names = [
        "002_qd5277_schema.sql",
        "003_seed_validation_data.sql",
        *[f"{number:03d}_{suffix}.sql" for number, suffix in (
            (4, "app_schema"),
            (5, "monthly_salt_sync"),
            (6, "official_admin_units"),
            (7, "ocop_init_only"),
            (8, "ocop_dynamic_criteria"),
            (9, "staff_role"),
            (10, "weekly_salt_imports"),
            (11, "weekly_foundation"),
            (12, "admin_units"),
            (13, "ocop_legacy_import"),
            (14, "qd5277_full_schema"),
            (15, "qd5333_non_spatial"),
            (16, "app_runtime_compatibility"),
            (17, "production_indexes"),
            (18, "repair_identity_sequences"),
            (19, "user_profiles"),
            (20, "activity_audit"),
            (20, "ocop_expiry_indexes"),
            (21, "hcmc_168_admin_units"),
            (22, "archive_legacy_users"),
        )],
    ]

    with psycopg.connect(
        host=settings.host,
        port=settings.port,
        dbname=settings.dbname,
        user=settings.user,
        password=settings.password,
        sslmode=settings.sslmode,
        autocommit=True,
        application_name="ptnt_production_bootstrap",
    ) as conn:
        is_empty = _target_is_empty(conn)
        if not is_empty:
            print("Bootstrap production: da khoi tao; bo qua (apply_pending se xu ly phan con thieu).")
            return 0
        sql_dir = ROOT / "database" / "sql"
        for name in migration_names:
            path = sql_dir / name
            if not path.is_file():
                raise RuntimeError(f"Khong tim thay migration: {path}")
            print(f"Dang ap dung {name} ...", flush=True)
            conn.execute(path.read_text(encoding="utf-8"))

    print("Bootstrap production: PASS (spatial QD5333 van PENDING_POSTGIS).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
