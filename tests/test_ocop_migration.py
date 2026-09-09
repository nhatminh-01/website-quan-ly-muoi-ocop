"""OCOP migration contracts, using only disposable in-memory databases.

Legacy DDL is read from the AST of server.py.  Neither server.py nor its
init_db/main functions are imported or executed by these tests.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import sqlite3
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ocop_migration_under_test", ROOT / "ocop_db.py")
ocop_db = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ocop_db)


LEGACY_TABLES = (
    "users", "records", "audit_logs", "DM_DonViHanhChinh",
    "DM_KhoangThoiGian", "DN_SanLuongMuoi",
)

EXPECTED_COLUMNS = {
    "schema_migrations": {"version", "applied_at"},
    "user_admin_units": {"user_id", "ma_don_vi_hanh_chinh"},
    "DM_SanPham": {"Ma_SanPham", "TenSanPham", "NhomSanPham", "DonViTinh", "TrangThai"},
    "DM_CoSo": {"Ma_CoSo", "TenCoSo", "LoaiCoSo", "DiaChi", "Ma_DonViHanhChinh"},
    "PTNT_OCOP": {
        "MA_OCOP", "Ma_DonViHanhChinh", "Ma_ThoiGian", "Ma_SanPham", "TenSanPham",
        "XepHang", "ChuTheSXKD", "DoanhThuNam", "TrangThai",
    },
    "ocop_entities": {
        "id", "ma_co_so", "representative_name", "phone", "email", "tax_code",
        "website", "description", "created_by", "created_at", "updated_at", "archived_at",
    },
    "ocop_products": {
        "id", "ma_san_pham", "ma_co_so", "ma_don_vi_hanh_chinh", "ten_san_pham",
        "product_group", "description", "current_star", "status", "created_by",
        "created_at", "updated_at", "criteria_set_id",
    },
    "ocop_applications": {
        "id", "product_id", "evaluation_type", "year", "status", "submitted_at",
        "checked_at", "reviewer_id", "reviewer_note", "created_by", "created_at",
        "updated_at", "revision", "submission_snapshot_json", "criteria_set_id",
    },
    "ocop_reviews": {"id", "application_id", "reviewer_id", "action", "comment", "created_at"},
    "ocop_criteria_sets": {
        "id", "code", "name", "product_category", "product_group", "product_subgroup",
        "legal_document", "version", "effective_from", "effective_to", "max_score",
        "active", "sort_order", "notes", "created_at", "updated_at",
    },
    "ocop_criteria": {
        "id", "criteria_set_id", "parent_id", "code", "title", "item_type",
        "section_code", "max_score", "requirement_text", "sort_order", "active",
    },
    "ocop_criteria_options": {
        "id", "criterion_id", "label", "score", "min_star", "is_eliminating",
        "evidence_hint", "sort_order", "active",
    },
}


def legacy_ddl():
    tree = ast.parse((ROOT / "server.py").read_text(encoding="utf-8-sig"))
    init = next(
        (node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "init_db"),
        None,
    )
    if init is None:
        raise AssertionError("Cannot locate init_db's legacy schema for isolated migration tests.")
    for node in ast.walk(init):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "executescript"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
            and "CREATE TABLE IF NOT EXISTS users" in node.args[0].value
        ):
            return node.args[0].value
    raise AssertionError("init_db must expose its legacy CREATE TABLE SQL as a literal.")


class OcopMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.legacy_sql = legacy_ddl()

    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.addCleanup(self.con.close)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys = ON")
        self.con.executescript(self.legacy_sql)
        self.con.executemany(
            "INSERT INTO users(id,username,password_hash,role,unit_name,active,created_at) "
            "VALUES(?,?,'synthetic-test-hash',?,?,?,'2026-01-01')",
            ((1, "fixture_admin", "admin", "Test administration", 1),
             (2, "fixture_unit", "unit", "Xã Mẫu A", 1)),
        )
        self.add_unit("90001", "Xã Mẫu A")
        self.con.execute(
            "INSERT INTO records(id,report_date,unit_name,created_by,harvest_land,status,"
            "note,created_at,updated_at) VALUES(1,'2026-01-02','Xã Mẫu A',2,12.5,"
            "'approved','existing salt report','2026-01-02','2026-01-02')"
        )
        self.con.execute(
            "INSERT INTO audit_logs(id,record_id,user_id,action,detail,created_at) "
            "VALUES(1,1,1,'original audit','must remain unchanged','2026-01-02')"
        )
        self.con.execute(
            "INSERT INTO DM_KhoangThoiGian(Ma_ThoiGian,Nam,Thang) VALUES('20260102',2026,1)"
        )
        self.con.execute(
            "INSERT INTO DN_SanLuongMuoi(Ma_DonViHanhChinh,Ma_ThoiGian,PhuongPhapSX,"
            "DienTich,SanLuong,GiaBanBinhQuan) VALUES('90001','20260102','Truyền thống',2,12.5,1000)"
        )
        self.con.commit()

    def add_unit(self, code, name, level="xa", active=1):
        self.con.execute(
            "INSERT INTO DM_DonViHanhChinh(Ma_DonViHanhChinh,TenDonVi,CapHanhChinh,TinhTrang) "
            "VALUES(?,?,?,?)", (code, name, level, active),
        )

    def add_user(self, user_id, name, active=1):
        self.con.execute(
            "INSERT INTO users(id,username,password_hash,role,unit_name,active,created_at) "
            "VALUES(?,?,'synthetic-test-hash','unit',?,?,'2026-01-01')",
            (user_id, f"fixture_unit_{user_id}", name, active),
        )

    def schema_snapshot(self):
        return [tuple(row) for row in self.con.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name"
        )]

    def legacy_snapshot(self):
        return {
            table: [tuple(row) for row in self.con.execute(f'SELECT * FROM "{table}" ORDER BY rowid')]
            for table in LEGACY_TABLES
        }

    def test_additive_schema_preserves_every_legacy_row_and_column(self):
        before = self.legacy_snapshot()
        old_columns = {
            table: [tuple(row) for row in self.con.execute(f'PRAGMA table_info("{table}")')]
            for table in LEGACY_TABLES
        }
        result = ocop_db.migrate(self.con)
        self.assertTrue(result["applied"])
        self.assertEqual(result["mapped_units"], 1)
        after = self.legacy_snapshot()
        for table in LEGACY_TABLES:
            with self.subTest(legacy_table=table):
                if table == "audit_logs":
                    self.assertEqual(after[table], [row + (None, None, None) for row in before[table]])
                else:
                    self.assertEqual(after[table], before[table])
                columns = [tuple(row) for row in self.con.execute(f'PRAGMA table_info("{table}")')]
                self.assertEqual(columns[:len(old_columns[table])], old_columns[table])
                self.assertEqual(len(columns), len(old_columns[table]) + (3 if table == "audit_logs" else 0))
        self.assertEqual(self.con.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual(self.con.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM PTNT_OCOP").fetchone()[0], 0)

    def test_complete_stage_two_contract(self):
        ocop_db.migrate(self.con)
        tables = {row[0] for row in self.con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual(tables - set(LEGACY_TABLES) - {"sqlite_sequence"}, set(EXPECTED_COLUMNS))
        for table, expected in EXPECTED_COLUMNS.items():
            with self.subTest(table=table):
                actual = {row[1] for row in self.con.execute(f'PRAGMA table_info("{table}")')}
                self.assertEqual(actual, expected)
                for foreign_key in self.con.execute(f'PRAGMA foreign_key_list("{table}")'):
                    self.assertEqual(foreign_key[6], "NO ACTION", "OCOP must never cascade-delete history")
        audit = {row[1]: tuple(row) for row in self.con.execute("PRAGMA table_info(audit_logs)")}
        for name in ("module", "object_type", "object_id"):
            self.assertEqual(audit[name][2:6], ("TEXT", 0, None, 0))

    def test_repeat_is_byte_identical_and_has_two_version_markers(self):
        ocop_db.migrate(self.con)
        before = self.con.serialize()
        original_changes = self.con.total_changes
        original_markers = [tuple(row) for row in self.con.execute("SELECT * FROM schema_migrations ORDER BY version")]
        result = ocop_db.migrate(self.con)
        self.assertFalse(result["applied"])
        self.assertEqual(result["mapped_units"], 0)
        self.assertEqual(self.con.serialize(), before)
        self.assertEqual(self.con.total_changes, original_changes)
        self.assertEqual([tuple(row) for row in self.con.execute("SELECT * FROM schema_migrations ORDER BY version")], original_markers)
        self.assertEqual([row[0] for row in original_markers], [ocop_db.FOUNDATION_VERSION, ocop_db.MIGRATION_VERSION])

    def test_stage_two_seeds_26_dynamic_sets_and_three_score_sections_each(self):
        ocop_db.migrate(self.con)
        sets = [dict(row) for row in self.con.execute(
            "SELECT * FROM ocop_criteria_sets ORDER BY sort_order"
        )]
        self.assertEqual(len(sets), 26)
        self.assertEqual([row["code"] for row in sets], [f"QD26-{i:02d}" for i in range(1, 27)])
        self.assertEqual(sets[9]["name"], "Gia vị khác (muối, hành, tỏi, tiêu)")
        self.assertEqual(sets[9]["product_category"], "Thực phẩm")
        self.assertEqual(sets[9]["product_group"], "Gia vị")
        self.assertTrue(all(row["legal_document"] == "26/2026/QĐ-TTg" for row in sets))
        self.assertTrue(all(row["effective_from"] == "2026-05-22" for row in sets))
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM ocop_criteria").fetchone()[0], 78)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM ocop_criteria_options").fetchone()[0], 0)
        totals = self.con.execute(
            "SELECT criteria_set_id,COUNT(*),SUM(max_score) FROM ocop_criteria GROUP BY criteria_set_id"
        ).fetchall()
        self.assertEqual(len(totals), 26)
        self.assertTrue(all(count == 3 and float(total) == 100.0 for _sid, count, total in totals))
        self.assertEqual(
            [tuple(row) for row in self.con.execute(
                "SELECT code,max_score FROM ocop_criteria WHERE criteria_set_id=? ORDER BY sort_order",
                (sets[9]["id"],),
            )],
            [("A", 40.0), ("B", 25.0), ("C", 35.0)],
        )

    def test_stage_two_links_are_nullable_and_preserve_preexisting_ocop_rows(self):
        # Build the phase-one tables explicitly, put rows in them, then let migrate add phase two.
        for sql in ocop_db.TABLES.values():
            self.con.execute(sql)
        self.con.execute("ALTER TABLE audit_logs ADD COLUMN module TEXT")
        self.con.execute("ALTER TABLE audit_logs ADD COLUMN object_type TEXT")
        self.con.execute("ALTER TABLE audit_logs ADD COLUMN object_id TEXT")
        self.con.execute(
            "INSERT INTO DM_CoSo(Ma_CoSo,TenCoSo,LoaiCoSo,Ma_DonViHanhChinh) VALUES('CSOLD','Cơ sở cũ','Hợp tác xã','90001')"
        )
        self.con.execute(
            "INSERT INTO ocop_entities(ma_co_so,created_by,created_at,updated_at) VALUES('CSOLD',2,'old','old')"
        )
        self.con.execute("INSERT INTO DM_SanPham(Ma_SanPham,TenSanPham,NhomSanPham) VALUES('SPOLD','Sản phẩm cũ','Nhóm cũ')")
        self.con.execute(
            """INSERT INTO ocop_products(ma_san_pham,ma_co_so,ma_don_vi_hanh_chinh,ten_san_pham,product_group,description,status,created_by,created_at,updated_at)
               VALUES('SPOLD','CSOLD','90001','Sản phẩm cũ','Nhóm cũ','','active',2,'old','old')"""
        )
        product_id = self.con.execute("SELECT id FROM ocop_products WHERE ma_san_pham='SPOLD'").fetchone()[0]
        self.con.execute(
            """INSERT INTO ocop_applications(product_id,evaluation_type,year,status,created_by,created_at,updated_at)
               VALUES(?,'new',2026,'draft',2,'old','old')""", (product_id,)
        )
        self.con.execute(
            "INSERT INTO schema_migrations(version,applied_at) VALUES(?, 'old')", (ocop_db.FOUNDATION_VERSION,)
        )
        self.con.commit()
        before_product = tuple(self.con.execute("SELECT * FROM ocop_products").fetchone())
        before_application = tuple(self.con.execute("SELECT * FROM ocop_applications").fetchone())
        result = ocop_db.migrate(self.con)
        self.assertEqual(result["versions_applied"], [ocop_db.MIGRATION_VERSION])
        after_product = tuple(self.con.execute("SELECT * FROM ocop_products").fetchone())
        after_application = tuple(self.con.execute("SELECT * FROM ocop_applications").fetchone())
        self.assertEqual(after_product, before_product + (None,))
        self.assertEqual(after_application, before_application + (None,))

    def test_conflicting_seed_is_refused_without_overwrite(self):
        ocop_db.migrate(self.con)
        self.con.execute("UPDATE ocop_criteria_sets SET name='Sai dữ liệu' WHERE code='QD26-10'")
        self.con.commit()
        before = self.con.serialize()
        with self.assertRaisesRegex(ocop_db.MigrationError, "QD26-10"):
            ocop_db.migrate(self.con)
        self.assertEqual(self.con.serialize(), before)

    def test_partial_table_is_rejected_without_changes(self):
        self.con.execute("CREATE TABLE ocop_entities(id INTEGER PRIMARY KEY)")
        before = self.con.serialize()
        with self.assertRaisesRegex(ocop_db.MigrationError, "ocop_entities"):
            ocop_db.migrate(self.con)
        self.assertEqual(self.con.serialize(), before)

    def test_incompatible_audit_column_rolls_back_new_tables_and_other_columns(self):
        self.con.execute("ALTER TABLE audit_logs ADD COLUMN object_id INTEGER")
        before = self.con.serialize()
        with self.assertRaisesRegex(ocop_db.MigrationError, "audit_logs.object_id"):
            ocop_db.migrate(self.con)
        self.assertEqual(self.con.serialize(), before)

    def test_failure_after_ddl_rolls_back_every_change(self):
        before = self.con.serialize()

        def fail_new_index(action, name, _table, _database, _source):
            if action == sqlite3.SQLITE_CREATE_INDEX and name.startswith("IX_OCOP_"):
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        self.con.set_authorizer(fail_new_index)
        try:
            with self.assertRaises(sqlite3.DatabaseError):
                ocop_db.migrate(self.con)
        finally:
            self.con.set_authorizer(None)
        self.assertEqual(self.con.serialize(), before)

    def test_caller_can_rollback_migration_with_its_transaction(self):
        before = self.con.serialize()
        self.con.execute("BEGIN")
        self.con.execute("UPDATE records SET note='pending caller change' WHERE id=1")
        ocop_db.migrate(self.con)
        self.assertTrue(self.con.in_transaction)
        self.con.rollback()
        self.assertEqual(self.con.serialize(), before)

    def test_failure_preserves_uncommitted_caller_work(self):
        self.con.execute("CREATE TABLE ocop_entities(id INTEGER PRIMARY KEY)")
        self.con.execute("UPDATE records SET note='pending caller change' WHERE id=1")
        with self.assertRaises(ocop_db.MigrationError):
            ocop_db.migrate(self.con)
        self.assertTrue(self.con.in_transaction)
        self.assertEqual(self.con.execute("SELECT note FROM records WHERE id=1").fetchone()[0], "pending caller change")

    def test_foreign_keys_must_be_enabled_before_migration(self):
        self.con.execute("PRAGMA foreign_keys=OFF")
        before = self.con.serialize()
        with self.assertRaisesRegex(ocop_db.MigrationError, "foreign_keys"):
            ocop_db.migrate(self.con)
        self.assertEqual(self.con.serialize(), before)

    def test_unit_mapping_requires_unique_exact_active_non_temporary_commune(self):
        self.add_unit("90002", "Xã Trùng")
        self.add_unit("90003", "Xã Trùng", "phuong")
        self.add_unit("TMP00001", "Xã Tạm")
        self.add_unit("90004", "Xã Không hoạt động", active=0)
        self.add_unit("90005", "Tỉnh Mẫu", level="tinh")
        cases = (
            (3, "Xã Trùng", 1), (4, "Xã Không có", 1), (5, "Xã Tạm", 1),
            (6, "Xã Không hoạt động", 1), (7, "Tỉnh Mẫu", 1),
            (8, " Xã Mẫu A", 1), (9, "xã Mẫu A", 1), (10, "Xã Mẫu A", 0),
        )
        for user_id, name, active in cases:
            self.add_user(user_id, name, active)
        self.con.commit()
        ocop_db.migrate(self.con)
        self.assertEqual([tuple(row) for row in self.con.execute("SELECT * FROM user_admin_units")], [(2, "90001")])
        self.add_unit("90006", "Phường Đã xác minh", level="phuong")
        self.con.execute("UPDATE user_admin_units SET ma_don_vi_hanh_chinh='90006' WHERE user_id=2")
        self.con.commit()
        ocop_db.migrate(self.con)
        self.assertEqual(self.con.execute("SELECT ma_don_vi_hanh_chinh FROM user_admin_units WHERE user_id=2").fetchone()[0], "90006")

    def official_fixture(self):
        ocop_db.migrate(self.con)
        self.con.execute("INSERT INTO DM_KhoangThoiGian(Ma_ThoiGian,Nam) VALUES('2026',2026)")
        self.con.execute("INSERT INTO DM_SanPham(Ma_SanPham,TenSanPham) VALUES('SP1','Sản phẩm mẫu')")

    def add_official(self, revenue, star="3*", status="valid"):
        self.con.execute(
            "INSERT INTO PTNT_OCOP(Ma_DonViHanhChinh,Ma_ThoiGian,Ma_SanPham,TenSanPham,"
            "XepHang,ChuTheSXKD,DoanhThuNam,TrangThai) VALUES(?,?,?,?,?,?,?,?)",
            ("90001", "2026", "SP1", "Sản phẩm mẫu", star, "Chủ thể mẫu", revenue, status),
        )

    def test_official_revenue_is_numeric_finite_nonnegative_and_within_decimal_precision(self):
        self.official_fixture()
        for invalid in (None, -1, float("inf"), float("-inf"), float("nan"), "not a number", 1_000_000_000_000, 0.001):
            with self.subTest(revenue=invalid), self.assertRaises(sqlite3.IntegrityError):
                self.add_official(invalid)
        for valid in (0, 0.01, 100.25, 999_999_999_999.99):
            with self.subTest(revenue=valid):
                self.add_official(valid)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM PTNT_OCOP").fetchone()[0], 4)

    def test_official_stars_and_status_length_without_inventing_status_enum(self):
        self.official_fixture()
        for invalid in ("1*", "2*", "3", "5", "draft", ""):
            with self.subTest(star=invalid), self.assertRaises(sqlite3.IntegrityError):
                self.add_official(10, star=invalid)
        for valid in ("3*", "4*", "5*"):
            self.add_official(10, star=valid, status="CUSTOM")
        for invalid in ("", "12345678901"):
            with self.subTest(status=invalid), self.assertRaises(sqlite3.IntegrityError):
                self.add_official(10, status=invalid)

    def test_master_code_rejects_null_empty_and_more_than_ten_characters(self):
        ocop_db.migrate(self.con)
        for invalid in (None, "", "12345678901"):
            with self.subTest(product_code=invalid), self.assertRaises(sqlite3.IntegrityError):
                self.con.execute("INSERT INTO DM_SanPham(Ma_SanPham,TenSanPham) VALUES(?,'Mẫu')", (invalid,))
            with self.subTest(entity_code=invalid), self.assertRaises(sqlite3.IntegrityError):
                self.con.execute(
                    "INSERT INTO DM_CoSo(Ma_CoSo,TenCoSo,LoaiCoSo,Ma_DonViHanhChinh) "
                    "VALUES(?,'Mẫu','Hợp tác xã','90001')", (invalid,),
                )
        self.con.execute("INSERT INTO DM_SanPham(Ma_SanPham,TenSanPham) VALUES('1234567890','Mẫu')")

    def test_foreign_keys_reject_unknown_official_product_or_administrative_scope(self):
        self.official_fixture()
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute("INSERT INTO user_admin_units(user_id,ma_don_vi_hanh_chinh) VALUES(999,'90001')")
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute(
                "INSERT INTO DM_CoSo(Ma_CoSo,TenCoSo,LoaiCoSo,Ma_DonViHanhChinh) "
                "VALUES('CS1','Mẫu','Hợp tác xã','MISSING')"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute(
                "INSERT INTO PTNT_OCOP(Ma_DonViHanhChinh,Ma_ThoiGian,Ma_SanPham,TenSanPham,"
                "XepHang,ChuTheSXKD,DoanhThuNam,TrangThai) "
                "VALUES('90001','2026','MISSING','Mẫu','3*','Mẫu',0,'valid')"
            )


if __name__ == "__main__":
    unittest.main()
