"""Idempotently migrate the legacy website SQLite data into PostgreSQL."""

from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row


DB_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = DB_DIR.parent / "salt_management.db"
ADMIN_UNITS = {
    "xã an thới đông": ("Xã An Thới Đông", "27673"),
    "xã an thời đông": ("Xã An Thới Đông", "27673"),
    "xã thạnh an": ("Xã Thạnh An", "27676"),
    "xã cần giờ": ("Xã Cần Giờ", "27664"),
    "xã long điền": ("Xã Long Điền", "26659"),
    "xã long sơn": ("Xã Long Sơn", "26545"),
    "phường phước thắng": ("Phường Phước Thắng", "26542"),
    "phường long hương": ("Phường Long Hương", "26566"),
    "phường bà rịa": ("Phường Bà Rịa", "26560"),
}


def canonical_unit(value):
    return ADMIN_UNITS.get(str(value or "").strip().casefold())


def pg_connect():
    load_dotenv(DB_DIR / ".env", override=False)
    return psycopg.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=int(os.getenv("PGPORT", "5432")),
        dbname=os.getenv("PGDATABASE", "ptnt_qd5277_dev"),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD") or None,
        row_factory=dict_row,
        options="-c search_path=app,qd5277,staging,public",
        application_name="ptnt_sqlite_migration",
    )


def source_rows(source, table):
    return [dict(row) for row in source.execute(f'SELECT * FROM "{table}" ORDER BY id')]


def reset_identity(target, table):
    target.execute(
        f"""SELECT setval(
            pg_get_serial_sequence('app.{table}', 'id'),
            COALESCE((SELECT MAX(id) + 1 FROM app.{table}), 1),
            FALSE)"""
    )


def migrate(source_path):
    source = sqlite3.connect(source_path)
    source.row_factory = sqlite3.Row
    users = source_rows(source, "users")
    records = source_rows(source, "records")
    audits = source_rows(source, "audit_logs")
    source.close()

    with pg_connect() as target:
        for row in users:
            canonical = canonical_unit(row["unit_name"])
            unit_name = canonical[0] if canonical else row["unit_name"]
            target.execute(
                """INSERT INTO app.users(id,username,role,unit_name,active,created_at)
                   VALUES(%s,%s,%s,%s,%s,%s)
                   ON CONFLICT(id) DO UPDATE SET
                     username=excluded.username, role=excluded.role,
                     unit_name=excluded.unit_name, active=excluded.active""",
                (row["id"], row["username"], row["role"], unit_name,
                 bool(row["active"]), row["created_at"]),
            )
            target.execute(
                """INSERT INTO app.user_credentials(user_id,password_hash)
                   VALUES(%s,%s)
                   ON CONFLICT(user_id) DO UPDATE SET password_hash=excluded.password_hash""",
                (row["id"], row["password_hash"]),
            )
            if row["role"] == "unit" and canonical:
                target.execute(
                    """INSERT INTO app.user_admin_units(user_id,ma_don_vi_hanh_chinh)
                       VALUES(%s,%s)
                       ON CONFLICT(user_id) DO UPDATE SET
                         ma_don_vi_hanh_chinh=excluded.ma_don_vi_hanh_chinh""",
                    (row["id"], canonical[1]),
                )

        record_columns = (
            "id", "report_date", "reporting_mode", "unit_name", "ma_don_vi_hanh_chinh",
            "created_by", "area_land", "area_tarp", "harvest_land", "harvest_tarp",
            "sold_land", "sold_tarp", "remaining_land", "remaining_tarp",
            "processed_fine", "processed_iodized", "households", "workers",
            "price_land", "price_tarp", "damage_land", "damage_tarp", "status",
            "note", "reviewer_note", "created_at", "updated_at", "submitted_at", "approved_at",
        )
        for row in records:
            canonical = canonical_unit(row["unit_name"])
            if not canonical:
                raise RuntimeError(f"Báo cáo dùng đơn vị chưa có mã chính thức: {row['unit_name']}")
            values = {
                **row,
                "reporting_mode": "cumulative",
                "unit_name": canonical[0],
                "ma_don_vi_hanh_chinh": canonical[1],
            }
            placeholders = ",".join(["%s"] * len(record_columns))
            updates = ",".join(
                f"{column}=excluded.{column}" for column in record_columns if column != "id"
            )
            target.execute(
                f"""INSERT INTO app.records({','.join(record_columns)})
                    VALUES({placeholders})
                    ON CONFLICT(id) DO UPDATE SET {updates}""",
                tuple(values.get(column) for column in record_columns),
            )

        for row in audits:
            target.execute(
                """INSERT INTO app.audit_logs
                   (id,record_id,user_id,action,detail,created_at)
                   VALUES(%s,%s,%s,%s,%s,%s)
                   ON CONFLICT(id) DO UPDATE SET
                     record_id=excluded.record_id, user_id=excluded.user_id,
                     action=excluded.action, detail=excluded.detail,
                     created_at=excluded.created_at""",
                tuple(row[column] for column in
                      ("id", "record_id", "user_id", "action", "detail", "created_at")),
            )

        for table in ("users", "records", "audit_logs"):
            reset_identity(target, table)

        target.execute(
            """INSERT INTO qd5277.DM_KhoangThoiGian(Ma_ThoiGian,Nam,Thang,VuMua)
               SELECT DISTINCT to_char(report_date,'YYYY-MM'),
                      EXTRACT(YEAR FROM report_date)::INTEGER,
                      EXTRACT(MONTH FROM report_date)::INTEGER, NULL
               FROM app.records WHERE status='approved' AND reporting_mode='cumulative'
               ON CONFLICT(Ma_ThoiGian) DO NOTHING"""
        )
        target.execute(
            """WITH latest AS (
                   SELECT r.*,
                          row_number() OVER (
                            PARTITION BY ma_don_vi_hanh_chinh, date_trunc('month',report_date)
                            ORDER BY report_date DESC,id DESC) AS position
                   FROM app.records r
                   WHERE status='approved' AND reporting_mode='cumulative'
                     AND ma_don_vi_hanh_chinh IS NOT NULL
               )
               INSERT INTO qd5277.DN_SanLuongMuoi
                   (Ma_DonViHanhChinh,Ma_ThoiGian,PhuongPhapSX,DienTich,SanLuong,GiaBanBinhQuan)
               SELECT ma_don_vi_hanh_chinh, to_char(report_date,'YYYY-MM'), 'Truyền thống',
                      area_land + area_tarp, harvest_land + harvest_tarp, NULL
               FROM latest WHERE position=1
               ON CONFLICT(Ma_DonViHanhChinh,Ma_ThoiGian,PhuongPhapSX) DO UPDATE SET
                   DienTich=excluded.DienTich,
                   SanLuong=excluded.SanLuong,
                   GiaBanBinhQuan=NULL"""
        )
        target.execute(
            """INSERT INTO app.schema_migrations(version)
               VALUES('app_004_sqlite_data') ON CONFLICT(version) DO NOTHING"""
        )

    return {"users": len(users), "records": len(records), "audit_logs": len(audits)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args()
    if not args.source.is_file():
        parser.error(f"Không tìm thấy SQLite nguồn: {args.source}")
    counts = migrate(args.source)
    print("Migration hoàn tất: " + ", ".join(f"{key}={value}" for key, value in counts.items()))


if __name__ == "__main__":
    main()
