"""Additive SQLite weekly schema upgrade. Never changes OCOP or legacy records."""
import argparse
import json
from pathlib import Path
import sqlite3

TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS salt_import_batches(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    file_sha256 TEXT NOT NULL,
    sheet_name TEXT NOT NULL,
    week_code TEXT NOT NULL,
    report_date TEXT NOT NULL,
    template_version TEXT NOT NULL DEFAULT 'weekly-v1',
    import_mode TEXT NOT NULL CHECK(import_mode IN ('skip','update')),
    total_rows INTEGER NOT NULL,
    warning_rows INTEGER NOT NULL DEFAULT 0,
    imported_rows INTEGER NOT NULL DEFAULT 0,
    updated_rows INTEGER NOT NULL DEFAULT 0,
    skipped_rows INTEGER NOT NULL DEFAULT 0,
    imported_by INTEGER NOT NULL REFERENCES users(id),
    imported_at TEXT NOT NULL,
    UNIQUE(file_sha256,sheet_name,week_code)
);
CREATE TABLE IF NOT EXISTS salt_weekly_import_rows(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES salt_import_batches(id) ON DELETE CASCADE,
    excel_row INTEGER NOT NULL,
    unit_name_raw TEXT NOT NULL,
    ma_don_vi_hanh_chinh TEXT,
    validation_status TEXT NOT NULL CHECK(validation_status IN ('valid','warning')),
    validation_messages_json TEXT NOT NULL DEFAULT '[]',
    raw_data_json TEXT NOT NULL,
    canonical_data_json TEXT NOT NULL,
    UNIQUE(batch_id,excel_row)
);
CREATE TABLE IF NOT EXISTS salt_weekly_records(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES salt_import_batches(id),
    week_code TEXT NOT NULL,
    report_date TEXT NOT NULL,
    unit_name TEXT NOT NULL,
    ma_don_vi_hanh_chinh TEXT NOT NULL REFERENCES DM_DonViHanhChinh(Ma_DonViHanhChinh),
    phuong_phap_sx TEXT NOT NULL DEFAULT 'Truyền thống',
    dien_tich REAL NOT NULL CHECK(dien_tich>=0),
    san_luong REAL NOT NULL CHECK(san_luong>=0),
    gia_ban_binh_quan REAL CHECK(gia_ban_binh_quan IS NULL OR gia_ban_binh_quan>=0),
    area_land REAL NOT NULL DEFAULT 0, area_tarp REAL NOT NULL DEFAULT 0,
    harvest_land REAL NOT NULL DEFAULT 0, harvest_tarp REAL NOT NULL DEFAULT 0,
    sold_total REAL NOT NULL DEFAULT 0 CHECK(sold_total>=0),
    remaining_total REAL NOT NULL DEFAULT 0 CHECK(remaining_total>=0),
    sold_land REAL NOT NULL DEFAULT 0, sold_tarp REAL NOT NULL DEFAULT 0,
    remaining_land REAL NOT NULL DEFAULT 0, remaining_tarp REAL NOT NULL DEFAULT 0,
    processed_fine REAL NOT NULL DEFAULT 0, processed_iodized REAL NOT NULL DEFAULT 0,
    households INTEGER NOT NULL DEFAULT 0, workers INTEGER NOT NULL DEFAULT 0,
    price_land TEXT NOT NULL DEFAULT '', price_tarp TEXT NOT NULL DEFAULT '',
    damage_land REAL NOT NULL DEFAULT 0, damage_tarp REAL NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '', created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    UNIQUE(ma_don_vi_hanh_chinh,week_code)
);
CREATE INDEX IF NOT EXISTS IX_SaltWeeklyRecordPeriod
    ON salt_weekly_records(week_code,ma_don_vi_hanh_chinh);
CREATE INDEX IF NOT EXISTS IX_SaltImportBatchPeriod
    ON salt_import_batches(week_code,imported_at);
"""

VIEW_SCHEMA = """
CREATE VIEW IF NOT EXISTS v_dn_sanluongmuoi_weekly_qd5277 AS
SELECT id AS Ma_SanLuongMuoi, ma_don_vi_hanh_chinh AS Ma_DonViHanhChinh,
       week_code AS Ma_ThoiGian, 'Truyền thống' AS PhuongPhapSX,
       area_land + area_tarp AS DienTich,
       harvest_land + harvest_tarp AS SanLuong,
       CAST(NULL AS REAL) AS GiaBanBinhQuan
FROM salt_weekly_records;
"""

SCHEMA = TABLE_SCHEMA + VIEW_SCHEMA


def migrate(con):
    """Upgrade atomically, including callers that already own a transaction."""
    con.execute("SAVEPOINT weekly_schema_upgrade")
    try:
        for statement in TABLE_SCHEMA.split(";"):
            if statement.strip():
                con.execute(statement)
        columns = {row[1] for row in con.execute("PRAGMA table_info(salt_weekly_records)")}
        # Early weekly builds only stored these totals in the winning raw batch.
        # Copy them once into the effective record without replaying skipped uploads.
        for total, left, right in (("sold_total", "sold_land", "sold_tarp"),
                                   ("remaining_total", "remaining_land", "remaining_tarp")):
            if total in columns:
                continue
            con.execute(f"ALTER TABLE salt_weekly_records ADD COLUMN {total} "
                        f"REAL NOT NULL DEFAULT 0 CHECK({total}>=0)")
            rows = con.execute(f"""SELECT r.id, r.{left}+r.{right},
                (SELECT s.canonical_data_json FROM salt_weekly_import_rows s
                 WHERE s.batch_id=r.batch_id AND s.ma_don_vi_hanh_chinh=r.ma_don_vi_hanh_chinh
                 ORDER BY s.id LIMIT 1)
                FROM salt_weekly_records r""").fetchall()
            for record_id, fallback, raw in rows:
                value = json.loads(raw).get(total) if raw else None
                con.execute(f"UPDATE salt_weekly_records SET {total}=? WHERE id=?",
                            (fallback if value is None else value, record_id))
        # Replacing a view changes no source rows; also repairs the old C/F projection.
        con.execute("DROP VIEW IF EXISTS v_dn_sanluongmuoi_weekly_qd5277")
        con.execute(VIEW_SCHEMA)
        con.execute("RELEASE SAVEPOINT weekly_schema_upgrade")
    except Exception:
        con.execute("ROLLBACK TO SAVEPOINT weekly_schema_upgrade")
        con.execute("RELEASE SAVEPOINT weekly_schema_upgrade")
        raise
    return "Weekly schema ready; OCOP and legacy salt records unchanged."


def main():
    parser = argparse.ArgumentParser(description="Nang cap weekly schema tren database TEST.")
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
