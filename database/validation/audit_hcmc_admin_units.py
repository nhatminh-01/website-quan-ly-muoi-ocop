"""Audit the HCMC administrative-unit catalog against repository reference data.

The audit is deliberately read-only.  It compares every canonical code even
when the row currently has the wrong parent, and reports references to rows
that are outside the canonical current catalog before a migration changes
anything.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
import sys
from typing import Any

from psycopg import sql

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import backend_db


DEFAULT_REFERENCE = ROOT / "database" / "reference" / "hcmc_admin_units_2025.csv"
EXPECTED_LEVELS = {"phuong", "xa", "dackhu"}


def load_reference(path: Path = DEFAULT_REFERENCE) -> dict[str, dict[str, str]]:
    """Load and validate the auditable four-column reference dataset."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        expected = ["code", "name", "level", "parent_code"]
        if reader.fieldnames != expected:
            raise ValueError(f"Reference columns must be {expected}, got {reader.fieldnames}")
        reference: dict[str, dict[str, str]] = {}
        for row in reader:
            code = (row["code"] or "").strip()
            normalized = {key: (row[key] or "").strip() for key in expected}
            if not code or code in reference:
                raise ValueError(f"Duplicate or blank reference code: {code!r}")
            if normalized["level"] not in EXPECTED_LEVELS:
                raise ValueError(f"Unsupported reference level for {code}: {normalized['level']}")
            if normalized["parent_code"] != "79":
                raise ValueError(f"Reference parent must be 79 for {code}")
            reference[code] = normalized

    counts = Counter(row["level"] for row in reference.values())
    expected_counts = Counter({"phuong": 113, "xa": 54, "dackhu": 1})
    if len(reference) != 168 or counts != expected_counts:
        raise ValueError(
            f"Reference must contain 168 rows (113 phuong, 54 xa, 1 dackhu); "
            f"got {len(reference)} rows and {dict(counts)}"
        )
    return reference


def _fetch_rows(connection, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        columns = [column.name for column in cursor.description]
        return [dict(row) if isinstance(row, dict) else dict(zip(columns, row))
                for row in cursor.fetchall()]


def _table_columns(connection) -> list[dict[str, Any]]:
    return _fetch_rows(
        connection,
        """
        SELECT c.table_schema, c.table_name, c.column_name
        FROM information_schema.columns AS c
        JOIN information_schema.tables AS t
          ON t.table_schema = c.table_schema AND t.table_name = c.table_name
        WHERE t.table_type = 'BASE TABLE'
          AND c.table_schema IN ('app', 'qd5333', 'qd5277', 'staging', 'public')
          AND lower(c.column_name) IN (
              'ma_donvihanhchinh', 'ma_don_vi_hanh_chinh',
              'unit_code', 'mapped_unit_code'
          )
        ORDER BY c.table_schema, c.table_name, c.column_name
        """,
    )


def _business_counts(connection) -> dict[str, int]:
    targets = (
        ("app", "ocop_products"),
        ("app", "records"),
        ("app", "user_admin_units"),
        ("app", "ocop_recognitions"),
        ("app", "salt_weekly_records"),
        ("staging", "ocop_import_rows"),
        ("staging", "salt_weekly_import_rows"),
        ("qd5277", "dn_sanluongmuoi"),
        ("qd5277", "ptnt_ocop"),
    )
    counts: dict[str, int] = {}
    for schema, table in targets:
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass(%s)", (f"{schema}.{table}",))
            if cursor.fetchone()[0] is None:
                continue
            identifier = sql.SQL(".").join((sql.Identifier(schema), sql.Identifier(table)))
            cursor.execute(sql.SQL("SELECT COUNT(*) FROM {table}").format(table=identifier))
            counts[f"{schema}.{table}"] = int(cursor.fetchone()[0])
    return counts


def _reference_counts(connection, columns: list[dict[str, Any]], extra_codes: set[str]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for item in columns:
        identifier = sql.SQL(".").join((
            sql.Identifier(item["table_schema"]),
            sql.Identifier(item["table_name"]),
        ))
        column = sql.Identifier(item["column_name"])
        query = sql.SQL("SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE {column} = ANY(%s)) AS extra_refs FROM {table}").format(
            column=column,
            table=identifier,
        )
        with connection.cursor() as cursor:
            cursor.execute(query, (list(extra_codes),))
            counts = cursor.fetchone()
            total, extra_refs = counts[0], counts[1]
        results.append({
            **item,
            "total": int(total),
            "extra_refs": int(extra_refs),
        })
    return results


def audit(connection, reference: dict[str, dict[str, str]]) -> dict[str, Any]:
    codes = list(reference)
    current_rows = _fetch_rows(
        connection,
        """
        SELECT ma_donvihanhchinh AS code, ma_donvicaptren AS parent_code,
               tendonvi AS name, caphanhchinh AS level, tinhtrang AS active
        FROM qd5277.dm_donvihanhchinh
        WHERE ma_donvicaptren = '79'
        ORDER BY ma_donvihanhchinh
        """,
    )
    tmp_rows = _fetch_rows(
        connection,
        """
        SELECT ma_donvihanhchinh AS code, ma_donvicaptren AS parent_code,
               tendonvi AS name, caphanhchinh AS level, tinhtrang AS active
        FROM qd5277.dm_donvihanhchinh
        WHERE upper(ma_donvihanhchinh) LIKE 'TMP%%'
        ORDER BY ma_donvihanhchinh
        """,
    )
    current = {str(row["code"]): row for row in current_rows}
    canonical_rows = _fetch_rows(
        connection,
        """
        SELECT ma_donvihanhchinh AS code, ma_donvicaptren AS parent_code,
               tendonvi AS name, caphanhchinh AS level, tinhtrang AS active
        FROM qd5277.dm_donvihanhchinh
        WHERE ma_donvihanhchinh = ANY(%s)
        """,
        (codes,),
    )
    present = {str(row["code"]): row for row in canonical_rows}
    missing = sorted(set(reference) - set(present), key=lambda value: int(value))
    extra = sorted(set(current) - set(reference), key=lambda value: int(value) if value.isdigit() else value)

    def mismatch(field: str) -> list[str]:
        return sorted(
            [code for code, expected in reference.items()
             if code in present and present[code][field] != expected[field]],
            key=int,
        )

    inactive = sorted(
        [code for code in reference if code in present and not present[code]["active"]],
        key=int,
    )
    table_columns = _table_columns(connection)
    tmp_codes = {str(row["code"]) for row in tmp_rows}
    return {
        "reference_count": len(reference),
        "reference_counts": dict(Counter(row["level"] for row in reference.values())),
        "current_count": len(current),
        "canonical_present_count": len(present),
        "missing_codes": missing,
        "extra_codes": extra,
        "wrong_name": mismatch("name"),
        "wrong_level": mismatch("level"),
        "wrong_parent_code": mismatch("parent_code"),
        "inactive_canonical_codes": inactive,
        "current_level_counts": dict(Counter(row["level"] for row in current.values())),
        "current_rows": current_rows,
        "tmp_rows": tmp_rows,
        "business_counts": _business_counts(connection),
        "reference_counts_by_code": {code: reference[code] for code in sorted(reference, key=int)},
        "related_columns": _reference_counts(connection, table_columns, set(extra)),
        "tmp_related_columns": _reference_counts(connection, table_columns, tmp_codes),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--json", action="store_true", help="Print the complete machine-readable report")
    args = parser.parse_args()
    reference = load_reference(args.reference)
    with backend_db.connect(autocommit=True) as connection:
        report = audit(connection, reference)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        for key in (
            "reference_count", "current_count", "canonical_present_count",
            "missing_codes", "extra_codes", "wrong_name", "wrong_level",
            "wrong_parent_code", "inactive_canonical_codes", "current_level_counts",
        ):
            print(f"{key}: {report[key]}")
        print("related_columns:")
        for item in report["related_columns"]:
            print(f"  {item['table_schema']}.{item['table_name']}.{item['column_name']}: "
                  f"total={item['total']} extra_refs={item['extra_refs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
