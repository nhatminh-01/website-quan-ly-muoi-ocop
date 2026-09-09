"""Additive OCOP stage-one schema migration.

Importing this module never opens a database.  The caller must supply an
explicit SQLite connection with foreign-key enforcement enabled.
"""

from __future__ import annotations

import re
import sqlite3


MIGRATION_VERSION = "ocop_001_foundation"


class MigrationError(RuntimeError):
    """The existing schema cannot safely receive the OCOP migration."""


TABLES = {
    "schema_migrations": """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT NOT NULL PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
    """,
    "user_admin_units": """
        CREATE TABLE IF NOT EXISTS user_admin_units (
            user_id INTEGER NOT NULL PRIMARY KEY,
            ma_don_vi_hanh_chinh VARCHAR(10) NOT NULL
                CHECK(length(ma_don_vi_hanh_chinh) BETWEEN 1 AND 10),
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(ma_don_vi_hanh_chinh)
                REFERENCES DM_DonViHanhChinh(Ma_DonViHanhChinh)
        )
    """,
    "DM_SanPham": """
        CREATE TABLE IF NOT EXISTS DM_SanPham (
            Ma_SanPham VARCHAR(10) NOT NULL PRIMARY KEY
                CHECK(length(Ma_SanPham) BETWEEN 1 AND 10),
            TenSanPham NVARCHAR(255) NOT NULL
                CHECK(length(trim(TenSanPham)) BETWEEN 1 AND 255),
            NhomSanPham NVARCHAR(100) NOT NULL DEFAULT ''
                CHECK(length(NhomSanPham) <= 100),
            DonViTinh NVARCHAR(50) NOT NULL DEFAULT ''
                CHECK(length(DonViTinh) <= 50),
            TrangThai BOOLEAN NOT NULL DEFAULT 1 CHECK(TrangThai IN (0, 1))
        )
    """,
    "DM_CoSo": """
        CREATE TABLE IF NOT EXISTS DM_CoSo (
            Ma_CoSo VARCHAR(10) NOT NULL PRIMARY KEY
                CHECK(length(Ma_CoSo) BETWEEN 1 AND 10),
            TenCoSo NVARCHAR(255) NOT NULL
                CHECK(length(trim(TenCoSo)) BETWEEN 1 AND 255),
            LoaiCoSo NVARCHAR(100) NOT NULL
                CHECK(length(trim(LoaiCoSo)) BETWEEN 1 AND 100),
            DiaChi NVARCHAR(255) NOT NULL DEFAULT '' CHECK(length(DiaChi) <= 255),
            Ma_DonViHanhChinh VARCHAR(10) NOT NULL
                CHECK(length(Ma_DonViHanhChinh) BETWEEN 1 AND 10),
            FOREIGN KEY(Ma_DonViHanhChinh)
                REFERENCES DM_DonViHanhChinh(Ma_DonViHanhChinh)
        )
    """,
    "PTNT_OCOP": """
        CREATE TABLE IF NOT EXISTS PTNT_OCOP (
            MA_OCOP INTEGER NOT NULL PRIMARY KEY,
            Ma_DonViHanhChinh VARCHAR(10) NOT NULL
                CHECK(length(Ma_DonViHanhChinh) BETWEEN 1 AND 10),
            Ma_ThoiGian VARCHAR(10) NOT NULL
                CHECK(length(Ma_ThoiGian) BETWEEN 1 AND 10),
            Ma_SanPham VARCHAR(10) NOT NULL
                CHECK(length(Ma_SanPham) BETWEEN 1 AND 10),
            TenSanPham NVARCHAR(255) NOT NULL
                CHECK(length(trim(TenSanPham)) BETWEEN 1 AND 255),
            XepHang NVARCHAR(50) NOT NULL CHECK(XepHang IN ('3*', '4*', '5*')),
            ChuTheSXKD NVARCHAR(255) NOT NULL
                CHECK(length(trim(ChuTheSXKD)) BETWEEN 1 AND 255),
            DoanhThuNam DECIMAL(14,2) NOT NULL
                CHECK(typeof(DoanhThuNam) IN ('integer', 'real')
                    AND DoanhThuNam >= 0 AND DoanhThuNam <= 999999999999.99
                    AND round(DoanhThuNam, 2) = DoanhThuNam),
            TrangThai VARCHAR(10) NOT NULL
                CHECK(length(trim(TrangThai)) BETWEEN 1 AND 10),
            FOREIGN KEY(Ma_DonViHanhChinh)
                REFERENCES DM_DonViHanhChinh(Ma_DonViHanhChinh),
            FOREIGN KEY(Ma_ThoiGian) REFERENCES DM_KhoangThoiGian(Ma_ThoiGian),
            FOREIGN KEY(Ma_SanPham) REFERENCES DM_SanPham(Ma_SanPham)
        )
    """,
    "ocop_entities": """
        CREATE TABLE IF NOT EXISTS ocop_entities (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            ma_co_so VARCHAR(10) NOT NULL UNIQUE
                CHECK(length(ma_co_so) BETWEEN 1 AND 10),
            representative_name TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL DEFAULT '',
            email TEXT NOT NULL DEFAULT '',
            tax_code TEXT NOT NULL DEFAULT '',
            website TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            created_by INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            archived_at TEXT,
            FOREIGN KEY(ma_co_so) REFERENCES DM_CoSo(Ma_CoSo),
            FOREIGN KEY(created_by) REFERENCES users(id)
        )
    """,
    "ocop_products": """
        CREATE TABLE IF NOT EXISTS ocop_products (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            ma_san_pham VARCHAR(10) NOT NULL
                CHECK(length(ma_san_pham) BETWEEN 1 AND 10),
            ma_co_so VARCHAR(10) NOT NULL
                CHECK(length(ma_co_so) BETWEEN 1 AND 10),
            ma_don_vi_hanh_chinh VARCHAR(10) NOT NULL
                CHECK(length(ma_don_vi_hanh_chinh) BETWEEN 1 AND 10),
            ten_san_pham NVARCHAR(255) NOT NULL
                CHECK(length(trim(ten_san_pham)) BETWEEN 1 AND 255),
            product_group NVARCHAR(100) NOT NULL
                CHECK(length(trim(product_group)) BETWEEN 1 AND 100),
            description TEXT NOT NULL DEFAULT '',
            current_star INTEGER CHECK(current_star IS NULL OR
                (typeof(current_star) = 'integer' AND current_star IN (3, 4, 5))),
            status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'archived')),
            created_by INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(ma_san_pham) REFERENCES DM_SanPham(Ma_SanPham),
            FOREIGN KEY(ma_co_so) REFERENCES DM_CoSo(Ma_CoSo),
            FOREIGN KEY(ma_don_vi_hanh_chinh)
                REFERENCES DM_DonViHanhChinh(Ma_DonViHanhChinh),
            FOREIGN KEY(created_by) REFERENCES users(id)
        )
    """,
    "ocop_applications": """
        CREATE TABLE IF NOT EXISTS ocop_applications (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            evaluation_type TEXT NOT NULL
                CHECK(evaluation_type IN ('new', 're_evaluation', 'upgrade')),
            year INTEGER NOT NULL CHECK(typeof(year) = 'integer' AND year BETWEEN 1900 AND 9999),
            status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN (
                'draft', 'submitted', 'checking', 'returned', 'eligible',
                'scoring', 'completed', 'cancelled')),
            submitted_at TEXT,
            checked_at TEXT,
            reviewer_id INTEGER,
            reviewer_note TEXT NOT NULL DEFAULT '',
            created_by INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            revision INTEGER NOT NULL DEFAULT 1
                CHECK(typeof(revision) = 'integer' AND revision >= 1),
            submission_snapshot_json TEXT,
            FOREIGN KEY(product_id) REFERENCES ocop_products(id),
            FOREIGN KEY(reviewer_id) REFERENCES users(id),
            FOREIGN KEY(created_by) REFERENCES users(id)
        )
    """,
    "ocop_reviews": """
        CREATE TABLE IF NOT EXISTS ocop_reviews (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            application_id INTEGER NOT NULL,
            reviewer_id INTEGER NOT NULL,
            action TEXT NOT NULL CHECK(length(trim(action)) > 0),
            comment TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(application_id) REFERENCES ocop_applications(id),
            FOREIGN KEY(reviewer_id) REFERENCES users(id)
        )
    """,
}


INDEXES = (
    "CREATE INDEX IF NOT EXISTS IX_OCOP_UserUnit ON user_admin_units(ma_don_vi_hanh_chinh)",
    "CREATE INDEX IF NOT EXISTS IX_OCOP_CoSoUnit ON DM_CoSo(Ma_DonViHanhChinh, TenCoSo)",
    "CREATE INDEX IF NOT EXISTS IX_OCOP_EntityCreatedBy ON ocop_entities(created_by)",
    "CREATE INDEX IF NOT EXISTS IX_OCOP_ProductUnit ON ocop_products(ma_don_vi_hanh_chinh, status, id)",
    "CREATE INDEX IF NOT EXISTS IX_OCOP_ProductEntity ON ocop_products(ma_co_so)",
    "CREATE INDEX IF NOT EXISTS IX_OCOP_ProductMaster ON ocop_products(ma_san_pham)",
    "CREATE INDEX IF NOT EXISTS IX_OCOP_ProductGroup ON ocop_products(product_group, status)",
    "CREATE INDEX IF NOT EXISTS IX_OCOP_ApplicationProduct ON ocop_applications(product_id, year, status)",
    "CREATE INDEX IF NOT EXISTS IX_OCOP_ApplicationStatus ON ocop_applications(status, year, id)",
    "CREATE INDEX IF NOT EXISTS IX_OCOP_ReviewApplication ON ocop_reviews(application_id, id)",
    "CREATE INDEX IF NOT EXISTS IX_OCOP_OfficialScope ON PTNT_OCOP(Ma_DonViHanhChinh, Ma_ThoiGian, XepHang)",
    "CREATE INDEX IF NOT EXISTS IX_OCOP_OfficialProduct ON PTNT_OCOP(Ma_SanPham)",
)


def _declarations(sql):
    """Split this module's CREATE TABLE statements at top-level commas."""
    body = sql[sql.index("(") + 1:sql.rindex(")")]
    declarations, start, depth = [], 0, 0
    for position, character in enumerate(body):
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        elif character == "," and depth == 0:
            declarations.append(body[start:position].strip())
            start = position + 1
    declarations.append(body[start:].strip())
    return declarations


def _normalized_sql(value):
    return re.sub(r"\s+", "", value).replace('"', '').replace('`', '')


def _check_existing_table(con, name, sql):
    existing = con.execute(
        "SELECT type, sql FROM sqlite_master WHERE lower(name)=lower(?)", (name,)
    ).fetchone()
    if existing is None:
        return
    if existing[0] != "table":
        raise MigrationError(f"{name} phải là bảng, không phải VIEW hoặc đối tượng khác.")

    # Require every original declaration, but permit added columns from later
    # additive migrations.  Refuse incompatible partial tables instead of
    # silently accepting CREATE TABLE IF NOT EXISTS against an unsafe schema.
    actual = {_normalized_sql(item) for item in _declarations(existing[1])}
    expected = {_normalized_sql(item) for item in _declarations(sql)}
    if not expected.issubset(actual):
        raise MigrationError(
            f"Cấu trúc bảng {name} không tương thích hoặc chưa đầy đủ; "
            "cần kiểm tra migration riêng. Không tự tạo lại bảng."
        )


def _require_legacy_schema(con):
    required = {
        "users": {"id", "role", "unit_name", "active"},
        "audit_logs": {"id", "record_id", "user_id", "action", "detail", "created_at"},
        "DM_DonViHanhChinh": {"Ma_DonViHanhChinh", "TenDonVi", "CapHanhChinh", "TinhTrang"},
        "DM_KhoangThoiGian": {"Ma_ThoiGian", "Nam"},
    }
    for name, columns in required.items():
        present = {row[1] for row in con.execute(f'PRAGMA table_info("{name}")')}
        if not columns.issubset(present):
            raise MigrationError(f"Thiếu cấu trúc Diêm nghiệp bắt buộc trong bảng {name}.")


def _extend_audit(con):
    columns = {row[1].casefold(): row for row in con.execute('PRAGMA table_info("audit_logs")')}
    for name in ("module", "object_type", "object_id"):
        if name in columns:
            row = columns[name]
            if row[2].upper() != "TEXT" or row[3] or row[4] is not None or row[5]:
                raise MigrationError(f"Cột audit_logs.{name} phải là TEXT nullable, không có mặc định.")
        else:
            con.execute(f'ALTER TABLE audit_logs ADD COLUMN "{name}" TEXT')


def _map_exact_units(con):
    # BINARY is intentional: no lower-casing, trimming, fuzzy matching or TMP
    # generation.  An unmapped user receives no OCOP unit scope.
    rows = con.execute("""
        SELECT u.id, min(d.Ma_DonViHanhChinh)
        FROM users u
        JOIN DM_DonViHanhChinh d ON u.unit_name = d.TenDonVi COLLATE BINARY
        WHERE u.role = 'unit' AND u.active = 1
          AND d.TinhTrang = 1 AND d.CapHanhChinh IN ('xa', 'phuong')
          AND length(d.Ma_DonViHanhChinh) BETWEEN 1 AND 10
          AND upper(d.Ma_DonViHanhChinh) NOT LIKE 'TMP%'
          AND NOT EXISTS (SELECT 1 FROM user_admin_units m WHERE m.user_id = u.id)
        GROUP BY u.id
        HAVING count(*) = 1
    """).fetchall()
    for user_id, unit_code in rows:
        con.execute(
            "INSERT INTO user_admin_units(user_id, ma_don_vi_hanh_chinh) VALUES(?, ?)",
            (user_id, unit_code),
        )
    return len(rows)


def migrate(con: sqlite3.Connection):
    """Apply OCOP foundation atomically to the caller's explicit connection.

    Existing Diem-nghiep rows and tables are never rewritten.  The only ALTER
    adds nullable audit metadata, leaving every old audit value untouched.
    A surrounding caller transaction is preserved through a SAVEPOINT.
    """
    if not isinstance(con, sqlite3.Connection):
        raise TypeError("migrate() cần một kết nối SQLite được truyền rõ ràng.")
    if con.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        raise MigrationError("Kết nối migration phải bật PRAGMA foreign_keys = ON.")

    savepoint = "ocop_foundation_migration"
    con.execute(f"SAVEPOINT {savepoint}")
    try:
        _require_legacy_schema(con)
        for name, sql in TABLES.items():
            _check_existing_table(con, name, sql)
        for sql in TABLES.values():
            con.execute(sql)
        _extend_audit(con)
        for sql in INDEXES:
            con.execute(sql)
        mapped_units = _map_exact_units(con)
        cursor = con.execute(
            "INSERT INTO schema_migrations(version, applied_at) "
            "VALUES(?, strftime('%Y-%m-%d %H:%M:%S', 'now')) "
            "ON CONFLICT(version) DO NOTHING",
            (MIGRATION_VERSION,),
        )
        applied = cursor.rowcount == 1
        con.execute(f"RELEASE SAVEPOINT {savepoint}")
        return {"version": MIGRATION_VERSION, "applied": applied, "mapped_units": mapped_units}
    except Exception:
        con.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
        con.execute(f"RELEASE SAVEPOINT {savepoint}")
        raise
