"""Archived commune accounts remain historical identities, never login accounts.

PostgreSQL/HTTP fixtures own disposable databases. No production data is touched.
"""
import os
from pathlib import Path
import unittest

import backend_db
import repositories
import server
import test_profile_http as fixtures
import test_user_profiles as database_fixtures


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "database/sql/022_archive_legacy_users.sql"
STAMP = "2026-09-18 08:00:00"


def apply_migrations(con, *, before_archive=False):
    for path in sorted((ROOT / "database/sql").glob("[0-9][0-9][0-9]_*.sql")):
        if path.name[:3] in ("001", "003") or (before_archive and path.name[:3] >= "022"):
            continue
        con.execute(path.read_text(encoding="utf-8"))


def seed_history(con, uid):
    """Exercise real FKs, including author/reviewer identities and locality mapping."""
    con.execute("INSERT INTO app.user_admin_units(user_id,ma_don_vi_hanh_chinh) VALUES(%s,'27595')", (uid,))
    con.execute("INSERT INTO app.user_profiles(user_id,full_name,agency_name) VALUES(%s,'Cán bộ xã cũ','Xã Tân Nhựt')", (uid,))
    record_id = con.execute(
        """INSERT INTO app.records(report_date,unit_name,ma_don_vi_hanh_chinh,created_by,
               area_land,area_tarp,harvest_land,harvest_tarp,created_at,updated_at)
           VALUES('2025-01-02','Xã Tân Nhựt','27595',%s,70,30,600,400,%s,%s) RETURNING id""",
        (uid, STAMP, STAMP),
    ).fetchone()[0]
    con.execute(
        "INSERT INTO app.audit_logs(record_id,user_id,action,detail,created_at) VALUES(%s,%s,'historical_fixture','Bản ghi phải giữ nguyên',%s)",
        (record_id, uid, STAMP),
    )
    con.execute("INSERT INTO qd5277.dm_coso(ma_coso,tencoso,loaicoso,ma_donvihanhchinh) VALUES('CSARCHIVE','Chủ thể lịch sử','HTX','27595')")
    con.execute("INSERT INTO qd5277.dm_sanpham(ma_sanpham,tensanpham,nhomsanpham,donvitinh,trangthai) VALUES('SPARCHIVE','Sản phẩm lịch sử','Thực phẩm','',TRUE)")
    con.execute(
        "INSERT INTO app.ocop_entities(ma_co_so,created_by,created_at,updated_at) VALUES('CSARCHIVE',%s,%s,%s)",
        (uid, STAMP, STAMP),
    )
    product_id = con.execute(
        """INSERT INTO app.ocop_products(ma_san_pham,ma_co_so,ma_don_vi_hanh_chinh,ten_san_pham,
               product_group,created_by,created_at,updated_at)
           VALUES('SPARCHIVE','CSARCHIVE','27595','Sản phẩm lịch sử','Thực phẩm',%s,%s,%s) RETURNING id""",
        (uid, STAMP, STAMP),
    ).fetchone()[0]
    application_id = con.execute(
        """INSERT INTO app.ocop_applications(product_id,evaluation_type,year,reviewer_id,created_by,created_at,updated_at)
           VALUES(%s,'new',2025,%s,%s,%s,%s) RETURNING id""",
        (product_id, uid, uid, STAMP, STAMP),
    ).fetchone()[0]
    con.execute(
        "INSERT INTO app.ocop_reviews(application_id,reviewer_id,action,comment,created_at) VALUES(%s,%s,'historical_fixture','Nhận xét lịch sử',%s)",
        (application_id, uid, STAMP),
    )
    con.execute(
        "INSERT INTO app.user_identities(user_id,provider,subject) VALUES(%s,'historical_fixture','identity-kept')", (uid,),
    )


def history_snapshot(con, uid):
    filters = {
        "records": ("created_by=%s", (uid,)),
        "audit_logs": ("user_id=%s AND action='historical_fixture'", (uid,)),
        "user_admin_units": ("user_id=%s", (uid,)),
        "user_credentials": ("user_id=%s", (uid,)),
        "user_identities": ("user_id=%s", (uid,)),
        "user_profiles": ("user_id=%s", (uid,)),
        "ocop_entities": ("created_by=%s", (uid,)),
        "ocop_products": ("created_by=%s", (uid,)),
        "ocop_applications": ("created_by=%s OR reviewer_id=%s", (uid, uid)),
        "ocop_reviews": ("reviewer_id=%s", (uid,)),
    }
    return {
        name: [dict(row) for row in con.execute("SELECT * FROM app." + name + " WHERE " + where, args).fetchall()]
        for name, (where, args) in filters.items()
    }


@unittest.skipUnless(os.getenv("OCOP_TEST_PG_DSN"), "Requires disposable PostgreSQL databases")
class LegacyMigrationTests(unittest.TestCase):
    connection = database_fixtures.UserProfilePostgreSQLTests.connection
    drop_database = database_fixtures.UserProfilePostgreSQLTests.drop_database

    def setUp(self):
        database_fixtures.UserProfilePostgreSQLTests.setUp(self)
        with self.connection() as con:
            apply_migrations(con, before_archive=True)
            # Only this disposable fixture permits the literal historical role.
            # Production does not gain an option to create legacy accounts.
            con.execute("ALTER TABLE app.users DROP CONSTRAINT users_role_check")
            con.execute("ALTER TABLE app.users ADD CONSTRAINT users_role_check CHECK(role IN ('admin','staff','unit','legacy'))")
            self.ids = {}
            for name, role, active in (("old_unit", "unit", True), ("old_legacy", "legacy", True),
                                       ("internal_admin", "admin", True), ("internal_staff", "staff", True),
                                       ("disabled_staff", "staff", False)):
                self.ids[name] = con.execute(
                    "INSERT INTO app.users(username,role,unit_name,active,created_at) VALUES(%s,%s,'Xã Tân Nhựt',%s,%s) RETURNING id",
                    (name, role, active, STAMP),
                ).fetchone()[0]
            uid = self.ids["old_unit"]
            con.execute("INSERT INTO app.user_credentials(user_id,password_hash) VALUES(%s,'historical-password-hash')", (uid,))
            seed_history(con, uid)

    def test_migration_twice_archives_all_old_roles_and_preserves_history(self):
        with self.connection() as con:
            before_users = [dict(row) for row in con.execute("SELECT * FROM app.users ORDER BY id")]
            before_history = history_snapshot(con, self.ids["old_unit"])
            self.assertTrue(all(before_history.values()))
            before_catalog = [dict(row) for row in con.execute("SELECT * FROM qd5277.dm_donvihanhchinh ORDER BY ma_donvihanhchinh")]
            for _ in range(2):
                con.execute(MIGRATION.read_text(encoding="utf-8"))
                after_users = [dict(row) for row in con.execute("SELECT * FROM app.users ORDER BY id")]
                expected = [{**row, "active":False} if row["role"] in ("unit", "legacy") else row for row in before_users]
                self.assertEqual(after_users, expected)
                self.assertEqual(history_snapshot(con, self.ids["old_unit"]), before_history)
                self.assertEqual([dict(row) for row in con.execute("SELECT * FROM qd5277.dm_donvihanhchinh ORDER BY ma_donvihanhchinh")], before_catalog)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM app.schema_migrations WHERE version='app_022_archive_legacy_users'").fetchone()[0], 1)

    def test_database_blocks_reactivation_repurposing_and_deletion(self):
        with self.connection() as con:
            con.execute(MIGRATION.read_text(encoding="utf-8"))
            before = history_snapshot(con, self.ids["old_unit"])
            for role in ("unit", "legacy"):
                uid = self.ids["old_" + role]
                for statement, args in (
                    ("UPDATE app.users SET active=TRUE WHERE id=%s", (uid,)),
                    ("UPDATE app.users SET role='staff' WHERE id=%s", (uid,)),
                    ("UPDATE app.users SET username='reused_account' WHERE id=%s", (uid,)),
                    ("UPDATE app.users SET unit_name='Địa bàn khác' WHERE id=%s", (uid,)),
                    ("UPDATE app.users SET id=99999 WHERE id=%s", (uid,)),
                    ("DELETE FROM app.users WHERE id=%s", (uid,)),
                ):
                    with self.subTest(role=role, statement=statement), self.assertRaises(self.psycopg.errors.CheckViolation):
                        con.execute(statement, args)
                self.assertFalse(con.execute("SELECT active FROM app.users WHERE id=%s", (uid,)).fetchone()[0])
            self.assertEqual(history_snapshot(con, self.ids["old_unit"]), before)
            con.execute("UPDATE app.users SET active=FALSE WHERE id=%s", (self.ids["internal_staff"],))
            con.execute("UPDATE app.users SET active=TRUE WHERE id=%s", (self.ids["internal_staff"],))
            self.assertTrue(con.execute("SELECT active FROM app.users WHERE id=%s", (self.ids["internal_staff"],)).fetchone()[0])

    def test_imported_historical_accounts_are_always_inactive(self):
        with self.connection() as con:
            con.execute(MIGRATION.read_text(encoding="utf-8"))
            for role in ("unit", "legacy"):
                for explicit_active in (True, False):
                    row = con.execute(
                        "INSERT INTO app.users(username,role,active,created_at) VALUES(%s,%s,%s,%s) RETURNING id,active",
                        (f"import_{role}_{explicit_active}", role, explicit_active, STAMP),
                    ).fetchone()
                    self.assertFalse(row["active"])
            row = con.execute("INSERT INTO app.users(username,role,created_at) VALUES('import_default','unit',%s) RETURNING active", (STAMP,)).fetchone()
            self.assertFalse(row[0])


@unittest.skipUnless(os.getenv("OCOP_TEST_PG_DSN"), "Requires disposable PostgreSQL HTTP databases")
class LegacyAccountHTTPTests(unittest.TestCase):
    connection = fixtures.ProfileHTTPTests.connection
    drop_database = fixtures.ProfileHTTPTests.drop_database

    def setUp(self):
        fixtures.ProfileHTTPTests.setUp(self)
        with self.connection() as con:
            seed_history(con, self.ids["legacy_unit"])
        self.uid = self.ids["legacy_unit"]

    def test_default_list_is_internal_and_archive_filter_is_readonly(self):
        status, _, content = self.admin.request("GET", "/users")
        self.assertEqual(status, 200)
        self.assertIn("profile_admin", content)
        self.assertIn("profile_staff", content)
        self.assertNotIn("legacy_unit", content)
        self.assertIn("Hiện tài khoản xã/phường cũ", content)
        status, _, content = self.admin.request("GET", "/users?show_legacy=1")
        self.assertEqual(status, 200)
        page = fixtures.Page(content)
        rows = [node for node in page.nodes if node["tag"] == "tr" and node["attrs"].get("data-account-role") == "unit"]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertIn("legacy_unit", row["text"])
        for text in ("Tài khoản xã/phường (cũ)", "Chỉ lưu lịch sử", "Ngừng hoạt động"):
            self.assertIn(text, row["text"])
        self.assertFalse([node for node in page.nodes if row in node["parents"] and node["tag"] in ("a", "form", "button")])
        for text in ("Kích hoạt", "Ngưng kích hoạt"):
            self.assertNotIn(text, row["text"])
        with self.connection() as con:
            compat = backend_db.CompatConnection(con)
            self.assertEqual({row["role"] for row in repositories.list_users(compat)}, {"admin", "staff"})
            self.assertEqual({row["role"] for row in repositories.list_users(compat, include_legacy=True)}, {"admin", "staff", "unit"})
        self.assertEqual(self.staff.request("GET", "/users?show_legacy=1")[0], 403)

    def test_legacy_password_login_and_preexisting_session_are_rejected(self):
        legacy = fixtures.Client(self.http.server_address[1])
        self.assertEqual(legacy.request("POST", "/login", {"username":"legacy_unit", "password":"Profile-test-2026", "remember":"1"})[0], 401)
        with self.connection() as con:
            user = server.get_user(backend_db.CompatConnection(con), self.uid)
            self.assertFalse(user["active"])
        for method, path, data in (("GET", "/dashboard", None), ("GET", "/profile", None),
                                    ("POST", "/profile", {"full_name":"Không thể sử dụng lại"})):
            with self.subTest(method=method, path=path):
                sid = server.new_session(user)
                legacy.cookie = "salt_session=" + sid
                legacy.csrf = server.SESSIONS[sid]["csrf"]
                status, headers, _ = legacy.request(method, path, data)
                self.assertEqual(status, 303)
                self.assertIn(headers["Location"], ("/", "/login"))
                self.assertNotIn(sid, server.SESSIONS)
        self.assertEqual(self.admin.request("GET", "/profile")[0], 200)
        self.assertEqual(self.staff.request("GET", "/profile")[0], 200)

    def test_direct_admin_actions_cannot_repurpose_or_delete_archived_account(self):
        with self.connection() as con:
            before = history_snapshot(con, self.uid)
            before_user = dict(con.execute("SELECT * FROM app.users WHERE id=%s", (self.uid,)).fetchone())
        self.assertEqual(self.admin.request("GET", f"/users/{self.uid}/edit")[0], 403)
        for action in ("edit", "activate", "deactivate", "delete"):
            with self.subTest(action=action):
                status, _, _ = self.admin.request("POST", f"/users/{self.uid}/{action}", {
                    "username":"repurposed_account", "role":"admin", "active":"1", "password":"Replacement-2026",
                    "unit_name":"Đơn vị khác", "unit_code":"27673", "full_name":"Tên thay thế",
                })
                self.assertEqual(status, 403)
        with self.connection() as con:
            self.assertEqual(dict(con.execute("SELECT * FROM app.users WHERE id=%s", (self.uid,)).fetchone()), before_user)
            self.assertEqual(history_snapshot(con, self.uid), before)
        for role in ("unit", "legacy"):
            self.assertEqual(self.admin.request("POST", "/users/new", {"username":"new_" + role, "password":"Replacement-2026", "role":role})[0], 400)

    def test_repository_write_guards_preserve_archived_credentials_and_identity(self):
        with self.connection() as con:
            compat = backend_db.CompatConnection(con)
            before = history_snapshot(con, self.uid)
            for action in (
                lambda: repositories.set_user_active(compat, self.uid, True),
                lambda: repositories.update_user(compat, self.uid, "reused", "staff", "Địa bàn khác", True),
                lambda: repositories.set_local_password(compat, self.uid, "new-hash"),
                lambda: repositories.delete_user(compat, self.uid),
            ):
                with self.subTest(action=action), self.assertRaises(repositories.ArchivedAccountError):
                    action()
            self.assertEqual(history_snapshot(con, self.uid), before)

    def test_catalog_name_correction_keeps_archived_account_inactive_and_mapping_intact(self):
        status, _, _ = self.admin.request("POST", "/admin-units/27595/edit", {
            "code":"27595", "name":"Xã Tân Nhựt (hiệu chỉnh tên)", "level":"xa", "parent_code":"79",
        })
        self.assertEqual(status, 303)
        with self.connection() as con:
            row = con.execute("SELECT active,unit_name FROM app.users WHERE id=%s", (self.uid,)).fetchone()
            self.assertFalse(row["active"])
            self.assertEqual(row["unit_name"], "Xã Tân Nhựt (hiệu chỉnh tên)")
            self.assertEqual(con.execute("SELECT ma_don_vi_hanh_chinh FROM app.user_admin_units WHERE user_id=%s", (self.uid,)).fetchone()[0], "27595")
            self.assertEqual(con.execute("SELECT unit_name FROM app.records WHERE created_by=%s", (self.uid,)).fetchone()[0], "Xã Tân Nhựt")


@unittest.skipUnless(os.getenv("OCOP_TEST_BROWSER") and os.getenv("OCOP_TEST_PG_DSN"), "Runs in PostgreSQL Chromium CI")
class LegacyAccountBrowserTests(unittest.TestCase):
    connection = fixtures.ProfileHTTPTests.connection
    drop_database = fixtures.ProfileHTTPTests.drop_database
    setUp = fixtures.ProfileHTTPTests.setUp

    def test_archive_filter_and_mobile_rows_preserve_readonly_history(self):
        from playwright.sync_api import sync_playwright, expect
        origin = f"http://127.0.0.1:{self.http.server_address[1]}"
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = browser.new_context(viewport={"width":1440, "height":900})
                name, value = self.admin.cookie.split("=", 1)
                context.add_cookies([{"name":name, "value":value, "url":origin}])
                page = context.new_page()
                page.goto(origin + "/users")
                expect(page.locator('.users-table tr[data-account-role="unit"]')).to_have_count(0)
                page.get_by_role("link", name="Hiện tài khoản xã/phường cũ", exact=True).click()
                row = page.locator('.users-table tr[data-account-role="unit"]')
                expect(row).to_have_count(1)
                expect(row).to_contain_text("Chỉ lưu lịch sử")
                expect(row).to_contain_text("Ngừng hoạt động")
                expect(row.locator("a,button,form")).to_have_count(0)
                for width in (1440, 390, 320):
                    page.set_viewport_size({"width":width, "height":844})
                    page.wait_for_function("document.documentElement.scrollWidth <= innerWidth", timeout=5000)
                    expect(row).to_be_visible()
                    self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"), f"viewport={width}")
                context.close()
            finally:
                browser.close()
