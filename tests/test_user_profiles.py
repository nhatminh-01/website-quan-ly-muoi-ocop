from __future__ import annotations

import os
from pathlib import Path
import unittest
from uuid import uuid4

import backend_db
import user_profiles


ROOT = Path(__file__).resolve().parents[1]


class UserProfileUnitTests(unittest.TestCase):
    def test_profile_validation_fixes_agency_and_normalizes_fields(self):
        profile = user_profiles.validate_profile({
            "full_name": "  Nguyễn   Văn A  ",
            "job_title": " Chuyên viên ",
            "department": " Phòng Nghiệp vụ ",
            "phone": "0901 234 567",
            "official_email": "VAN.A@EXAMPLE.GOV.VN",
            "agency_name": "Không được tin giá trị từ trình duyệt",
        })
        self.assertEqual(profile["full_name"], "Nguyễn Văn A")
        self.assertEqual(profile["official_email"], "van.a@example.gov.vn")
        self.assertEqual(profile["agency_name"], user_profiles.CHI_CUC_AGENCY_NAME)

    def test_profile_validation_rejects_bad_contact_fields(self):
        with self.assertRaises(user_profiles.ProfileError):
            user_profiles.validate_profile({"full_name": "A", "official_email": "khong-phai-email"})
        with self.assertRaises(user_profiles.ProfileError):
            user_profiles.validate_profile({"full_name": "A", "phone": "abcXYZ"})

    def test_shell_uses_full_name_and_adds_profile_navigation_once(self):
        source = (
            '<!doctype html><html><head><title>Thông tin cá nhân · Quản lý nghiệp vụ</title></head><body>'
            '<div class="account-name">chicuc</div><span class="account-avatar">C</span>'
            '<a class="sidebar-link" href="/change-password">Đổi mật khẩu</a></body></html>'
        )
        result = user_profiles.enhance_shell(
            source,
            {"username": "chicuc"},
            {"full_name": "Mai Nguyễn Nhật Minh"},
            lambda name: f"<{name}>",
        )
        self.assertIn("Mai Nguyễn Nhật Minh", result)
        self.assertIn('href="/profile"', result)
        self.assertIn('class="sidebar-link active"', result)
        self.assertEqual(result.count('href="/profile"'), 1)
        self.assertIn('class="account-avatar">M</span>', result)


@unittest.skipUnless(os.getenv("OCOP_TEST_PG_DSN"), "PostgreSQL integration test requires OCOP_TEST_PG_DSN")
class UserProfilePostgreSQLTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg import sql

        self.psycopg = psycopg
        self.admin_dsn = os.environ["OCOP_TEST_PG_DSN"]
        self.database = "profile_test_" + uuid4().hex
        with psycopg.connect(self.admin_dsn, autocommit=True) as admin:
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(self.database)))
        self.addCleanup(self.drop_database)

    def drop_database(self):
        from psycopg import sql
        with self.psycopg.connect(self.admin_dsn, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(self.database)))

    def connection(self):
        return self.psycopg.connect(
            self.admin_dsn,
            dbname=self.database,
            autocommit=True,
            row_factory=backend_db.hybrid_row,
            options="-c search_path=app,qd5277,staging,public",
        )

    def test_migration_seeds_internal_accounts_and_profile_can_be_saved(self):
        with self.connection() as con:
            for name in ("002_qd5277_schema.sql", "004_app_schema.sql", "009_staff_role.sql"):
                con.execute((ROOT / "database" / "sql" / name).read_text(encoding="utf-8"))
            uid = con.execute(
                "INSERT INTO app.users(username,role,unit_name,active,created_at) "
                "VALUES('profile_staff','staff','Chi cục',TRUE,'2026-09-16') RETURNING id"
            ).fetchone()[0]
            con.execute((ROOT / "database" / "sql" / "019_user_profiles.sql").read_text(encoding="utf-8"))
            compat = backend_db.CompatConnection(con)
            seeded = user_profiles.get_profile(compat, uid)
            self.assertEqual(seeded["agency_name"], user_profiles.CHI_CUC_AGENCY_NAME)
            user_profiles.save_profile(compat, uid, {
                "full_name": "Nguyễn Văn A",
                "job_title": "Chuyên viên",
                "department": "Phòng Nghiệp vụ",
                "phone": "0901234567",
                "official_email": "a@example.gov.vn",
            })
            saved = user_profiles.get_profile(compat, uid)
            self.assertEqual(saved["full_name"], "Nguyễn Văn A")
            self.assertEqual(saved["official_email"], "a@example.gov.vn")
            self.assertEqual(
                con.execute("SELECT COUNT(*) FROM app.schema_migrations WHERE version='app_019_user_profiles'").fetchone()[0],
                1,
            )
