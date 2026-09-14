"""Copy the approved runtime/canonical data from dev to production.

The copy is allow-listed and insert-only (``ON CONFLICT DO NOTHING``).  It
skips temporary ``TMP`` administrative codes and records those mappings in
the production ``app.code_mappings`` layer.  It never drops, truncates, or
overwrites production rows.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend_db import DatabaseSettings


def settings_from(path: Path) -> DatabaseSettings:
    values = dotenv_values(path)
    if not values:
        raise RuntimeError(f"Khong tim thay cau hinh: {path}")
    return DatabaseSettings(
        host=str(values.get("PGHOST") or "localhost"),
        port=int(values.get("PGPORT") or 5432),
        dbname=str(values.get("PGDATABASE") or ""),
        user=str(values.get("PGUSER") or ""),
        password=str(values.get("PGPASSWORD")) if values.get("PGPASSWORD") else None,
        sslmode=str(values.get("PGSSLMODE") or "prefer"),
    )


def connect(settings: DatabaseSettings, application_name: str):
    return psycopg.connect(
        host=settings.host, port=settings.port, dbname=settings.dbname,
        user=settings.user, password=settings.password, sslmode=settings.sslmode,
        autocommit=False, application_name=application_name,
    )


QD_TABLES = [
    "dm_khoangthoigian", "dm_donvihanhchinh", "dm_sanpham", "dm_coso",
    "dm_tieuchuanchatluong", "dm_tieuchuanhuuco", "dm_chitieuthongke",
    "dm_sieudulieu", "dm_donvi", "dm_thuoctinh", "dm_phicautruc",
    "dm_chatluongdulieu", "dm_phuongthucchiase", "dn_sanluongmuoi",
    "ptnt_ocop", "qlcl_cosochebien", "qlcl_attp", "qlcl_sanxuathuuco",
    "tt_thitruonggiaca",
]
APP_TABLES = [
    "users", "user_credentials", "user_identities", "user_admin_units",
    "admin_unit_aliases", "records", "audit_logs", "ocop_entities",
    "ocop_products", "ocop_criteria_sets", "ocop_criteria",
    "ocop_criteria_options", "ocop_applications", "ocop_reviews",
    "salt_import_batches", "salt_weekly_records",
]


def relation_exists(cur, schema: str, table: str) -> bool:
    cur.execute(
        """SELECT EXISTS (
               SELECT 1 FROM information_schema.tables
               WHERE table_schema=%s AND table_name=%s AND table_type='BASE TABLE'
           )""",
        (schema, table),
    )
    return bool(cur.fetchone()[0])


def columns(cur, schema: str, table: str) -> list[str]:
    cur.execute(
        """SELECT column_name FROM information_schema.columns
           WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position""",
        (schema, table),
    )
    return [row[0] for row in cur.fetchall()]


def column_types(cur, schema: str, table: str) -> dict[str, str]:
    cur.execute(
        """SELECT column_name, data_type FROM information_schema.columns
           WHERE table_schema=%s AND table_name=%s""",
        (schema, table),
    )
    return {name: data_type for name, data_type in cur.fetchall()}


def copy_table(source, target, schema: str, table: str, *, skip_tmp=False) -> int:
    with source.cursor() as scur, target.cursor() as tcur:
        if not relation_exists(tcur, schema, table) or not relation_exists(scur, schema, table):
            return 0
        source_columns = columns(scur, schema, table)
        target_columns = columns(tcur, schema, table)
        target_types = column_types(tcur, schema, table)
        common = [column for column in source_columns if column in target_columns]
        if not common:
            return 0
        query = sql.SQL("SELECT {fields} FROM {schema}.{table}").format(
            fields=sql.SQL(",").join(sql.Identifier(column) for column in common),
            schema=sql.Identifier(schema), table=sql.Identifier(table),
        )
        scur.execute(query)
        rows = scur.fetchall()
        if skip_tmp:
            key_index = common.index("ma_donvihanhchinh") if "ma_donvihanhchinh" in common else None
            if key_index is not None:
                rows = [row for row in rows if not str(row[key_index] or "").upper().startswith("TMP")]
        if not rows:
            return 0
        json_columns = {column for column in common if target_types.get(column) in ("json", "jsonb")}
        if json_columns:
            rows = [
                tuple(Jsonb(value) if column in json_columns and isinstance(value, (dict, list)) else value
                      for column, value in zip(common, row))
                for row in rows
            ]
        insert = sql.SQL("INSERT INTO {schema}.{table} ({fields}) VALUES ({values}) ON CONFLICT DO NOTHING").format(
            schema=sql.Identifier(schema), table=sql.Identifier(table),
            fields=sql.SQL(",").join(sql.Identifier(column) for column in common),
            values=sql.SQL(",").join(sql.Placeholder() for _ in common),
        )
        tcur.executemany(insert, rows)
        inserted = tcur.rowcount
        print(f"  {schema}.{table}: {inserted}/{len(rows)} row insert")
        return inserted


def copy_admin_code_mappings(source, target) -> int:
    with source.cursor() as scur, target.cursor() as tcur:
        if not relation_exists(scur, "app", "admin_unit_code_mapping"):
            return 0
        scur.execute(
            "SELECT temp_code,source_name,official_code FROM app.admin_unit_code_mapping"
        )
        rows = scur.fetchall()
        insert = sql.SQL(
            """INSERT INTO app.code_mappings
               (mapping_type,source_system,source_code,source_label,
                canonical_schema,canonical_table,canonical_code,note)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (mapping_type,source_system,source_code) DO NOTHING"""
        )
        values = [
            ("admin_unit", "legacy_import", temp, label or "",
             "qd5277", "DM_DonViHanhChinh", official,
             "Mapping ma TMP tu DB dev; khong dung lam khoa canonical")
            for temp, label, official in rows
            if temp and official
        ]
        if values:
            tcur.executemany(insert, values)
        inserted = tcur.rowcount if values else 0
        print(f"  app.code_mappings: {inserted}/{len(values)} row insert")
        return inserted


def reset_identity_sequences(target) -> None:
    with target.cursor() as cur:
        cur.execute(
            """
            SELECT table_schema, table_name, column_name
            FROM information_schema.columns
            WHERE table_schema IN ('app','staging')
              AND column_default LIKE 'nextval(%'
            """
        )
        for schema, table, column in cur.fetchall():
            cur.execute("SELECT pg_get_serial_sequence(%s,%s)", (f"{schema}.{table}", column))
            sequence = cur.fetchone()[0]
            if not sequence:
                continue
            cur.execute(
                sql.SQL("SELECT max({column}) FROM {schema}.{table}").format(
                    column=sql.Identifier(column), schema=sql.Identifier(schema), table=sql.Identifier(table)
                )
            )
            maximum = cur.fetchone()[0]
            if maximum is None:
                cur.execute("SELECT setval(%s, 1, false)", (sequence,))
            else:
                cur.execute("SELECT setval(%s, %s, true)", (sequence, maximum))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-env", default=str(ROOT / "database" / ".env"))
    parser.add_argument("--target-env", default=str(ROOT / "database" / ".env.production"))
    args = parser.parse_args()
    source_settings = settings_from(Path(args.source_env))
    target_settings = settings_from(Path(args.target_env))
    if source_settings.dbname == target_settings.dbname and source_settings.host == target_settings.host:
        raise RuntimeError("Source va production dang tro cung mot database; dung de tranh tu copy vao chinh no.")

    with connect(source_settings, "ptnt_dev_export") as source, connect(target_settings, "ptnt_production_data_migration") as target:
        for table in QD_TABLES:
            copy_table(source, target, "qd5277", table, skip_tmp=(table == "dm_donvihanhchinh"))
        for table in APP_TABLES:
            copy_table(source, target, "app", table, skip_tmp=(table == "user_admin_units"))
        # OCOP recognitions reference the source batch in staging, so copy
        # batches before recognitions and rows.
        copy_table(source, target, "staging", "diem_nghiep_2026_w34_raw")
        copy_table(source, target, "staging", "ocop_import_batches")
        copy_table(source, target, "app", "ocop_recognitions")
        copy_table(source, target, "staging", "ocop_import_rows")
        copy_table(source, target, "staging", "salt_weekly_import_rows")
        copy_admin_code_mappings(source, target)
        reset_identity_sequences(target)
        target.commit()

    print("Selective production data migration: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
