"""Additive OCOP schema migrations through phase two.

Importing this module never opens a database. The caller must supply an
explicit SQLite connection with foreign-key enforcement enabled.
"""

from __future__ import annotations

import re
import sqlite3


FOUNDATION_VERSION = "ocop_001_foundation"
MIGRATION_VERSION = "ocop_002_dynamic_criteria"


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


# OCOP stage two: the legal criteria catalogue is data, not 26 hard-coded forms.
# Detailed criterion/answer rows can be loaded incrementally in later migrations
# without changing product/application forms or the scoring engine.
STAGE2_TABLES = {
    "ocop_criteria_sets": """
        CREATE TABLE IF NOT EXISTS ocop_criteria_sets (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE CHECK(length(trim(code)) BETWEEN 1 AND 30),
            name TEXT NOT NULL CHECK(length(trim(name)) BETWEEN 1 AND 255),
            product_category TEXT NOT NULL CHECK(length(trim(product_category)) BETWEEN 1 AND 150),
            product_group TEXT NOT NULL CHECK(length(trim(product_group)) BETWEEN 1 AND 150),
            product_subgroup TEXT NOT NULL DEFAULT '' CHECK(length(product_subgroup) <= 255),
            legal_document TEXT NOT NULL CHECK(length(trim(legal_document)) BETWEEN 1 AND 100),
            version TEXT NOT NULL CHECK(length(trim(version)) BETWEEN 1 AND 50),
            effective_from TEXT NOT NULL CHECK(length(effective_from) = 10),
            effective_to TEXT,
            max_score REAL NOT NULL DEFAULT 100
                CHECK(typeof(max_score) IN ('integer','real') AND max_score > 0),
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
            sort_order INTEGER NOT NULL CHECK(typeof(sort_order)='integer' AND sort_order > 0),
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """,
    "ocop_criteria": """
        CREATE TABLE IF NOT EXISTS ocop_criteria (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            criteria_set_id INTEGER NOT NULL,
            parent_id INTEGER,
            code TEXT NOT NULL CHECK(length(trim(code)) BETWEEN 1 AND 50),
            title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 500),
            item_type TEXT NOT NULL CHECK(item_type IN ('section','group','criterion','note')),
            section_code TEXT CHECK(section_code IS NULL OR section_code IN ('A','B','C')),
            max_score REAL CHECK(max_score IS NULL OR
                (typeof(max_score) IN ('integer','real') AND max_score >= 0)),
            requirement_text TEXT NOT NULL DEFAULT '',
            sort_order INTEGER NOT NULL DEFAULT 0 CHECK(typeof(sort_order)='integer'),
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
            FOREIGN KEY(criteria_set_id) REFERENCES ocop_criteria_sets(id),
            FOREIGN KEY(parent_id) REFERENCES ocop_criteria(id),
            UNIQUE(criteria_set_id, code)
        )
    """,
    "ocop_criteria_options": """
        CREATE TABLE IF NOT EXISTS ocop_criteria_options (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            criterion_id INTEGER NOT NULL,
            label TEXT NOT NULL CHECK(length(trim(label)) BETWEEN 1 AND 2000),
            score REAL NOT NULL CHECK(typeof(score) IN ('integer','real') AND score >= 0),
            min_star INTEGER CHECK(min_star IS NULL OR min_star IN (3,4,5)),
            is_eliminating INTEGER NOT NULL DEFAULT 0 CHECK(is_eliminating IN (0,1)),
            evidence_hint TEXT NOT NULL DEFAULT '',
            sort_order INTEGER NOT NULL DEFAULT 0 CHECK(typeof(sort_order)='integer'),
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
            FOREIGN KEY(criterion_id) REFERENCES ocop_criteria(id)
        )
    """,
}

# Appendix I classification + Appendix II set names, Decision 26/2026/QD-TTg.
# Each tuple is: number, set name, broad category, group, subgroup.
CRITERIA_SET_SEED = (
    (1, "Rau, củ, quả, hạt tươi", "Thực phẩm", "Thực phẩm tươi sống", "Rau, củ, quả, hạt tươi"),
    (2, "Thịt, thủy sản, trứng, sữa tươi", "Thực phẩm", "Thực phẩm tươi sống", "Thịt, thủy sản, trứng, sữa tươi"),
    (3, "Gạo, ngũ cốc, hạt sơ chế khác", "Thực phẩm", "Thực phẩm thô, sơ chế", "Gạo, ngũ cốc, hạt sơ chế khác"),
    (4, "Mật ong, mật khác và nông sản thực phẩm khác", "Thực phẩm", "Thực phẩm thô, sơ chế", "Mật ong, mật khác và nông sản thực phẩm khác"),
    (5, "Đồ ăn nhanh", "Thực phẩm", "Thực phẩm chế biến", "Đồ ăn nhanh"),
    (6, "Chế biến từ gạo, ngũ cốc", "Thực phẩm", "Thực phẩm chế biến", "Chế biến từ gạo, ngũ cốc"),
    (7, "Chế biến từ rau, củ, quả, hạt", "Thực phẩm", "Thực phẩm chế biến", "Chế biến từ rau, củ, quả, hạt"),
    (8, "Chế biến từ thịt, thủy sản, trứng, sữa, các sản phẩm từ mật ong, mật khác và nông sản thực phẩm khác", "Thực phẩm", "Thực phẩm chế biến", "Chế biến từ thịt, trứng, sữa, thủy sản và nông sản thực phẩm khác"),
    (9, "Tương, nước mắm, gia vị dạng lỏng khác", "Thực phẩm", "Gia vị", "Tương, nước mắm, gia vị dạng lỏng khác"),
    (10, "Gia vị khác (muối, hành, tỏi, tiêu)", "Thực phẩm", "Gia vị", "Gia vị khác"),
    (11, "Chè tươi, chè chế biến", "Thực phẩm", "Chè", "Chè tươi, chế biến"),
    (12, "Sản phẩm trà từ thực vật khác", "Thực phẩm", "Chè", "Sản phẩm chè từ thực vật khác"),
    (13, "Cà phê, cacao", "Thực phẩm", "Cà phê, ca cao", ""),
    (14, "Rượu trắng", "Đồ uống", "Đồ uống có cồn", "Rượu trắng"),
    (15, "Đồ uống có cồn khác", "Đồ uống", "Đồ uống có cồn", "Đồ uống có cồn khác"),
    (16, "Nước khoáng thiên nhiên, nước uống đóng chai", "Đồ uống", "Đồ uống không cồn", "Nước khoáng thiên nhiên, nước uống đóng chai"),
    (17, "Đồ uống không cồn khác", "Đồ uống", "Đồ uống không cồn", "Đồ uống không cồn"),
    (18, "Thực phẩm chức năng, thuốc dược liệu, thuốc cổ truyền", "Dược liệu và sản phẩm từ dược liệu", "Thực phẩm chức năng, thuốc dược liệu, thuốc cổ truyền", ""),
    (19, "Mỹ phẩm có thành phần từ dược liệu", "Dược liệu và sản phẩm từ dược liệu", "Mỹ phẩm có thành phần từ dược liệu", ""),
    (20, "Tinh dầu và dược liệu khác", "Dược liệu và sản phẩm từ dược liệu", "Tinh dầu và dược liệu khác", ""),
    (21, "Thủ công mỹ nghệ", "Hàng thủ công mỹ nghệ", "Thủ công mỹ nghệ gia dụng, trang trí", ""),
    (22, "Vải, may mặc", "Hàng thủ công mỹ nghệ", "Vải, may mặc", ""),
    (23, "Hoa", "Sinh vật cảnh", "Hoa", ""),
    (24, "Cây cảnh", "Sinh vật cảnh", "Cây cảnh", ""),
    (25, "Động vật cảnh", "Sinh vật cảnh", "Động vật cảnh", ""),
    (26, "Dịch vụ du lịch cộng đồng, du lịch sinh thái và điểm du lịch", "Dịch vụ du lịch cộng đồng, du lịch sinh thái và điểm du lịch", "Dịch vụ du lịch cộng đồng, du lịch sinh thái và điểm du lịch", ""),
)

CRITERIA_SECTION_SEED = (
    ("A", "Sản phẩm và sức mạnh của cộng đồng", 40.0, 10),
    ("B", "Khả năng tiếp thị", 25.0, 20),
    ("C", "Chất lượng sản phẩm", 35.0, 30),
)

STAGE2_INDEXES = (
    "CREATE UNIQUE INDEX IF NOT EXISTS UX_OCOP_CriteriaSetSort ON ocop_criteria_sets(sort_order)",
    "CREATE INDEX IF NOT EXISTS IX_OCOP_CriteriaSetActive ON ocop_criteria_sets(active,sort_order)",
    "CREATE INDEX IF NOT EXISTS IX_OCOP_CriteriaSetClass ON ocop_criteria_sets(product_category,product_group,active)",
    "CREATE INDEX IF NOT EXISTS IX_OCOP_CriteriaTree ON ocop_criteria(criteria_set_id,parent_id,sort_order,id)",
    "CREATE INDEX IF NOT EXISTS IX_OCOP_CriteriaOptions ON ocop_criteria_options(criterion_id,sort_order,id)",
    "CREATE INDEX IF NOT EXISTS IX_OCOP_ProductCriteriaSet ON ocop_products(criteria_set_id,status,id)",
    "CREATE INDEX IF NOT EXISTS IX_OCOP_ApplicationCriteriaSet ON ocop_applications(criteria_set_id,status,id)",
)

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


def _columns(con, table):
    return {row[1].casefold(): row for row in con.execute(f'PRAGMA table_info("{table}")')}


def _extend_stage2_columns(con):
    specifications = (
        ("ocop_products", "criteria_set_id", "INTEGER REFERENCES ocop_criteria_sets(id)"),
        ("ocop_applications", "criteria_set_id", "INTEGER REFERENCES ocop_criteria_sets(id)"),
    )
    for table, column, declaration in specifications:
        columns = _columns(con, table)
        if column.casefold() in columns:
            row = columns[column.casefold()]
            if row[2].upper() != "INTEGER" or row[3] or row[4] is not None or row[5]:
                raise MigrationError(f"Cột {table}.{column} phải là INTEGER nullable, không có mặc định.")
        else:
            con.execute(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {declaration}')


def _verify_seed_row(actual, expected, code):
    keys = ("name", "product_category", "product_group", "product_subgroup", "legal_document",
            "version", "effective_from", "effective_to", "max_score", "active", "sort_order")
    for key in keys:
        left = actual[key]
        right = expected[key]
        if key == "max_score":
            left, right = float(left), float(right)
        if left != right:
            raise MigrationError(
                f"Bộ tiêu chí {code} đã tồn tại nhưng khác dữ liệu chuẩn tại trường {key}; "
                "không tự ghi đè dữ liệu pháp lý."
            )


def _seed_criteria_catalog(con):
    timestamp = "2026-05-22 00:00:00"
    legal_document = "26/2026/QĐ-TTg"
    version = "2026.1"
    for number, name, category, group, subgroup in CRITERIA_SET_SEED:
        code = f"QD26-{number:02d}"
        expected = {
            "name": name,
            "product_category": category,
            "product_group": group,
            "product_subgroup": subgroup,
            "legal_document": legal_document,
            "version": version,
            "effective_from": "2026-05-22",
            "effective_to": None,
            "max_score": 100.0,
            "active": 1,
            "sort_order": number,
        }
        cursor = con.execute(
            """SELECT name,product_category,product_group,product_subgroup,legal_document,version,
                      effective_from,effective_to,max_score,active,sort_order
               FROM ocop_criteria_sets WHERE code=?""", (code,)
        )
        row = cursor.fetchone()
        if row is None:
            con.execute(
                """INSERT INTO ocop_criteria_sets(
                    code,name,product_category,product_group,product_subgroup,legal_document,
                    version,effective_from,effective_to,max_score,active,sort_order,notes,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,100,1,?, ?,?,?)""",
                (code, name, category, group, subgroup, legal_document, version, "2026-05-22", None,
                 number, "Khung bộ tiêu chí theo Phụ lục II; tiêu chí chi tiết được quản lý dạng dữ liệu động.",
                 timestamp, timestamp),
            )
            cursor = con.execute(
                """SELECT name,product_category,product_group,product_subgroup,legal_document,version,
                          effective_from,effective_to,max_score,active,sort_order
                   FROM ocop_criteria_sets WHERE code=?""", (code,)
            )
            row = cursor.fetchone()
        actual = dict(zip((col[0] for col in cursor.description), row))
        _verify_seed_row(actual, expected, code)
        set_id = con.execute("SELECT id FROM ocop_criteria_sets WHERE code=?", (code,)).fetchone()[0]
        for section_code, title, score, order in CRITERIA_SECTION_SEED:
            section = con.execute(
                """SELECT parent_id,title,item_type,section_code,max_score,requirement_text,sort_order,active
                   FROM ocop_criteria WHERE criteria_set_id=? AND code=?""", (set_id, section_code)
            ).fetchone()
            if section is None:
                con.execute(
                    """INSERT INTO ocop_criteria(
                        criteria_set_id,parent_id,code,title,item_type,section_code,max_score,
                        requirement_text,sort_order,active)
                       VALUES(?,NULL,?,?,'section',?,?, '',?,1)""",
                    (set_id, section_code, title, section_code, score, order),
                )
                section = con.execute(
                    """SELECT parent_id,title,item_type,section_code,max_score,requirement_text,sort_order,active
                       FROM ocop_criteria WHERE criteria_set_id=? AND code=?""", (set_id, section_code)
                ).fetchone()
            expected_section = (None, title, "section", section_code, score, "", order, 1)
            normalized = tuple(float(v) if i == 4 else v for i, v in enumerate(section))
            normalized_expected = tuple(float(v) if i == 4 else v for i, v in enumerate(expected_section))
            if normalized != normalized_expected:
                raise MigrationError(
                    f"Mục {section_code} của {code} đã tồn tại nhưng khác khung điểm chuẩn; không tự ghi đè."
                )


def _apply_stage2(con):
    for name, sql in STAGE2_TABLES.items():
        _check_existing_table(con, name, sql)
    for sql in STAGE2_TABLES.values():
        con.execute(sql)
    _extend_stage2_columns(con)
    for sql in STAGE2_INDEXES:
        con.execute(sql)
    _seed_criteria_catalog(con)


def migrate(con: sqlite3.Connection):
    """Apply OCOP migrations 1-2 atomically to an explicit SQLite connection.

    Phase 2 is additive: it creates the dynamic legal criteria catalogue and
    adds nullable criteria-set links to OCOP products/applications. Existing
    salt and OCOP business rows are not rewritten or guessed.
    """
    if not isinstance(con, sqlite3.Connection):
        raise TypeError("migrate() cần một kết nối SQLite được truyền rõ ràng.")
    if con.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        raise MigrationError("Kết nối migration phải bật PRAGMA foreign_keys = ON.")

    savepoint = "ocop_migrations"
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
        foundation_cursor = con.execute(
            "INSERT INTO schema_migrations(version, applied_at) "
            "VALUES(?, strftime('%Y-%m-%d %H:%M:%S', 'now')) "
            "ON CONFLICT(version) DO NOTHING",
            (FOUNDATION_VERSION,),
        )

        _apply_stage2(con)
        stage2_cursor = con.execute(
            "INSERT INTO schema_migrations(version, applied_at) "
            "VALUES(?, strftime('%Y-%m-%d %H:%M:%S', 'now')) "
            "ON CONFLICT(version) DO NOTHING",
            (MIGRATION_VERSION,),
        )
        versions_applied = []
        if foundation_cursor.rowcount == 1:
            versions_applied.append(FOUNDATION_VERSION)
        if stage2_cursor.rowcount == 1:
            versions_applied.append(MIGRATION_VERSION)
        con.execute(f"RELEASE SAVEPOINT {savepoint}")
        return {
            "version": MIGRATION_VERSION,
            "applied": bool(versions_applied),
            "versions_applied": versions_applied,
            "mapped_units": mapped_units,
            "criteria_sets": len(CRITERIA_SET_SEED),
        }
    except Exception:
        con.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
        con.execute(f"RELEASE SAVEPOINT {savepoint}")
        raise

