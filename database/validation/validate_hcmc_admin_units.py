"""Validate the applied HCMC 2025 administrative-unit catalog."""
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import backend_db
from database.validation.audit_hcmc_admin_units import load_reference


def validate(connection, reference: dict[str, dict[str, str]]) -> dict[str, Any]:
    codes = list(reference)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT ma_donvihanhchinh AS code, ma_donvicaptren AS parent_code,
                   tendonvi AS name, caphanhchinh AS level, tinhtrang AS active
            FROM qd5277.dm_donvihanhchinh
            WHERE ma_donvihanhchinh = ANY(%s)
            """,
            (codes,),
        )
        rows = [dict(row) for row in cursor.fetchall()]
        cursor.execute(
            """
            SELECT caphanhchinh AS level, COUNT(*) AS total
            FROM qd5277.dm_donvihanhchinh
            WHERE ma_donvicaptren = '79'
              AND tinhtrang = TRUE
              AND ma_donvihanhchinh = ANY(%s)
            GROUP BY caphanhchinh
            """,
            (codes,),
        )
        counts = {row["level"]: int(row["total"]) for row in cursor.fetchall()}
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM qd5277.dm_donvihanhchinh
            WHERE upper(ma_donvihanhchinh) LIKE 'TMP%%'
              AND tinhtrang = TRUE
            """
        )
        active_tmp = int(cursor.fetchone()[0])
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM app.schema_migrations
            WHERE version = 'app_021_hcmc_168_admin_units'
            """
        )
        migration_recorded = int(cursor.fetchone()[0]) == 1

    actual = {str(row["code"]): row for row in rows}
    mismatches = []
    for code, expected in reference.items():
        row = actual.get(code)
        if row is None:
            mismatches.append({"code": code, "error": "missing"})
            continue
        for field in ("name", "level", "parent_code"):
            if row[field] != expected[field]:
                mismatches.append({
                    "code": code,
                    "field": field,
                    "expected": expected[field],
                    "actual": row[field],
                })
        if not row["active"]:
            mismatches.append({"code": code, "field": "active", "expected": True, "actual": False})

    expected_counts = {"phuong": 113, "xa": 54, "dackhu": 1}
    return {
        "total": sum(counts.values()),
        "counts": counts,
        "expected_counts": expected_counts,
        "special_unit": actual.get("26732"),
        "mismatches": mismatches,
        "active_tmp": active_tmp,
        "migration_recorded": migration_recorded,
        "pass": (
            len(actual) == 168
            and counts == expected_counts
            and not mismatches
            and active_tmp == 0
            and migration_recorded
        ),
    }


def main() -> int:
    reference = load_reference()
    with backend_db.connect(autocommit=True) as connection:
        result = validate(connection, reference)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
