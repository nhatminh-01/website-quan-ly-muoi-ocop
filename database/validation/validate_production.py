"""Validate the production canonical/runtime database and write a report."""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend_db import load_settings

QD5277_EXPECTED = {
    "dm_donvihanhchinh", "dm_khoangthoigian", "dm_sanpham", "dm_coso",
    "dm_tieuchuanchatluong", "dm_tieuchuanhuuco", "dm_chitieuthongke",
    "dn_sanluongmuoi", "ptnt_ocop", "qlcl_cosochebien", "qlcl_attp",
    "qlcl_sanxuathuuco", "tt_thitruonggiaca", "dm_sieudulieu", "dm_donvi",
    "dm_thuoctinh", "dm_phicautruc", "dm_chatluongdulieu", "dm_phuongthucchiase",
    "th_tonghop", "nn_trongtrot_tonghop", "nn_bvtv_tonghop", "nn_channuoi_tonghop",
    "nn_thuy_tonghop", "ln_dientichrung", "ln_sanphamlamnghiep",
    "ts_nuoitrong", "ts_khaithac", "tl_antoandap_hochuathuyloi",
    "tl_congtrinhthuyloi",
}
# PostgreSQL folds the unquoted identifiers in the migration to lowercase.

QD5333_NONSPATIAL_EXPECTED = {
    "cososanxuatmuoi", "baocaosxcbmuoi", "nhapkhaumuoi",
    "congbosanphammuoi", "lienkethoptacsxmuoi", "dm_nhomsanpham", "cososanxuat",
    "danhgiasanphamocop", "thuonghieubaoho", "thitruongtieuthu",
    "hotrophattriensanphamocop", "tochuchoatdongktht", "dm_phanloaimaythietbinn",
    "dm_loaihinhnganhnghe", "dm_sieudulieu", "dm_donvi", "dm_hetoado", "dm_thuoctinh",
    "dm_khonggian", "dm_phicautruc", "dm_chatluongdulieu", "dm_phuongthucchiase",
}
SPATIAL_PENDING = {
    "quyhoachdatlammuoi", "vungdatlammuoi", "khodutrumuoi", "sanphamocop",
}


def _table_names(cur, schema: str) -> set[str]:
    cur.execute(
        """
        SELECT table_name FROM information_schema.tables
        WHERE table_schema=%s AND table_type='BASE TABLE'
        """,
        (schema,),
    )
    return {row[0] for row in cur.fetchall()}


def _pk_count(cur, schema: str, table: str) -> int:
    cur.execute(
        """
        SELECT COUNT(*) FROM pg_constraint c
        JOIN pg_class t ON t.oid=c.conrelid
        JOIN pg_namespace n ON n.oid=t.relnamespace
        WHERE c.contype='p' AND n.nspname=%s AND t.relname=%s
        """,
        (schema, table),
    )
    return int(cur.fetchone()[0])


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", default=str(ROOT / "database" / ".env.production"))
    parser.add_argument("--report", default=str(ROOT / "database" / "validation" / "production_schema_report.md"))
    args = parser.parse_args()
    settings = load_settings(args.env_file)
    with psycopg.connect(
        host=settings.host, port=settings.port, dbname=settings.dbname,
        user=settings.user, password=settings.password, sslmode=settings.sslmode,
        autocommit=True, application_name="ptnt_production_validation",
    ) as conn:
        with conn.cursor() as cur:
            qd5277 = _table_names(cur, "qd5277")
            qd5333 = _table_names(cur, "qd5333")
            cur.execute("SELECT current_database(), current_user, current_setting('server_version')")
            db, user, version = cur.fetchone()
            cur.execute("SELECT EXISTS (SELECT 1 FROM pg_available_extensions WHERE name='postgis')")
            postgis_available = bool(cur.fetchone()[0])
            cur.execute("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname='postgis')")
            postgis_enabled = bool(cur.fetchone()[0])
            cur.execute("SELECT COUNT(*) FROM app.schema_migrations")
            migration_count = int(cur.fetchone()[0])
            qd5277_pk = sum(_pk_count(cur, "qd5277", name) for name in qd5277)
            qd5333_pk = sum(_pk_count(cur, "qd5333", name) for name in qd5333)
            cur.execute(
                """SELECT n.nspname, COUNT(*)::INTEGER
                   FROM pg_constraint c
                   JOIN pg_class t ON t.oid=c.conrelid
                   JOIN pg_namespace n ON n.oid=t.relnamespace
                   WHERE c.contype='f' AND n.nspname IN ('app','qd5277','qd5333','staging')
                   GROUP BY n.nspname ORDER BY n.nspname"""
            )
            fk_counts = dict(cur.fetchall())
            cur.execute(
                """SELECT schemaname, COUNT(*)::INTEGER FROM pg_indexes
                   WHERE schemaname IN ('app','qd5277','qd5333','staging')
                   GROUP BY schemaname ORDER BY schemaname"""
            )
            index_counts = dict(cur.fetchall())
            data_tables = [
                ("app", "users"), ("app", "ocop_entities"), ("app", "ocop_products"),
                ("app", "ocop_recognitions"), ("app", "salt_weekly_records"),
                ("staging", "ocop_import_rows"), ("qd5277", "dm_donvihanhchinh"),
                ("qd5277", "dm_sanpham"), ("qd5277", "dm_coso"), ("qd5277", "ptnt_ocop"),
                ("app", "code_mappings"),
            ]
            data_counts = {}
            for schema, table in data_tables:
                cur.execute(
                    sql.SQL("SELECT count(*) FROM {}.{}").format(
                        sql.Identifier(schema), sql.Identifier(table)
                    )
                )
                data_counts[f"{schema}.{table}"] = int(cur.fetchone()[0])

    missing_5277 = sorted(QD5277_EXPECTED - qd5277)
    extra_5277 = sorted(qd5277 - QD5277_EXPECTED)
    missing_5333 = sorted(QD5333_NONSPATIAL_EXPECTED - qd5333)
    extra_5333 = sorted(qd5333 - QD5333_NONSPATIAL_EXPECTED)
    pass_5277 = len(qd5277) == 30 and not missing_5277
    pass_5333 = len(qd5333) == 22 and not missing_5333
    report = f"""# Production schema report — {date.today().isoformat()}

## Kết nối

- Database: `{db}`
- User: `{user}`
- PostgreSQL: `{version}`
- Migration markers: `{migration_count}`

## Kết quả canonical

| Phạm vi | Mong đợi | Thực tế | Trạng thái |
|---|---:|---:|---|
| QĐ 5277 canonical | 30 | {len(qd5277)} | {'PASS' if pass_5277 else 'PARTIAL'} |
| QĐ 5333 non-spatial | 22 | {len(qd5333)} | {'PASS' if pass_5333 else 'PARTIAL'} |
| QĐ 5333 spatial | 4 | 0 | PENDING_POSTGIS |

### QĐ 5277

- PK constraints found: `{qd5277_pk}`
- Missing: `{', '.join(missing_5277) if missing_5277 else 'none'}`
- Unexpected: `{', '.join(extra_5277) if extra_5277 else 'none'}`

### QĐ 5333 non-spatial

- PK constraints found: `{qd5333_pk}`
- Missing: `{', '.join(missing_5333) if missing_5333 else 'none'}`
- Unexpected: `{', '.join(extra_5333) if extra_5333 else 'none'}`

## PostGIS

- Available in PostgreSQL catalog: `{postgis_available}`
- Enabled for application role: `{postgis_enabled}`
- Deferred tables: `QuyHoachDatLamMuoi`, `VungDatLamMuoi`, `KhoDuTruMuoi`, `SanPhamOCOP`
- Status: **PENDING_POSTGIS** (no fake geometry column and no SRID guessed)

## Ràng buộc và dữ liệu đã chuyển

- FK constraints theo schema: `{', '.join(f'{k}={v}' for k, v in fk_counts.items()) or 'none'}`
- Indexes theo schema: `{', '.join(f'{k}={v}' for k, v in index_counts.items()) or 'none'}`
- Row count mẫu sau migrate: `{', '.join(f'{k}={v}' for k, v in data_counts.items())}`

## Ghi chú

Các khác biệt/typo của QĐ được ghi tại `database/schema_issues.md`.
"""
    Path(args.report).write_text(report, encoding="utf-8")
    print(report)
    return 0 if pass_5277 and pass_5333 else 1


if __name__ == "__main__":
    raise SystemExit(main())
