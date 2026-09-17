"""Profile navigation, account integration and activity history through app_server."""
from html import escape
from html.parser import HTMLParser
import http.client
import os
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

import app_server
import backend_db
import ocop_pages
import server
import user_profiles
import test_user_profiles as profile_tests


class Page(HTMLParser):
    def __init__(self, content):
        super().__init__()
        self.stack = []
        self.nodes = []
        self.feed(content)

    def handle_starttag(self, tag, attributes):
        node = {"tag": tag, "attrs": dict(attributes), "parents": list(self.stack), "text": ""}
        self.nodes.append(node)
        if tag not in ("input", "img", "link", "meta", "br", "hr"):
            self.stack.append(node)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["tag"] == tag:
                self.stack = self.stack[:index]
                break

    def handle_data(self, data):
        for node in self.stack:
            node["text"] += data

    def by_class(self, name):
        return [node for node in self.nodes if name in node["attrs"].get("class", "").split()]

    def input(self, name):
        return next(node["attrs"] for node in self.nodes
                    if node["tag"] == "input" and node["attrs"].get("name") == name)

    def selected_option(self, name):
        select = next(node for node in self.nodes if node["tag"] == "select" and node["attrs"].get("name") == name)
        options = [node for node in self.nodes if node["tag"] == "option" and select in node["parents"]]
        selected = [node for node in options if "selected" in node["attrs"]]
        return (selected[0]["attrs"].get("value") if selected else "")


class ProfileHeaderTests(unittest.TestCase):
    def render(self, profile, role="staff"):
        session = {"user_id": 1, "username": "staff_test", "role": role, "unit_name": "Chi cục"}
        with patch.object(server, "ocop_available", return_value=False):
            content = server.base_page("Thông tin cá nhân", "", session, active_path="/profile")
        return user_profiles.enhance_shell(content, session, profile, server.icon)

    def test_full_name_role_avatar_and_dropdown_are_rendered(self):
        page = Page(self.render({"full_name": "Mai Nguyễn Nhật Minh"}))
        trigger = page.by_class("account-menu-trigger")[0]
        self.assertEqual(trigger["tag"], "button")
        self.assertEqual(trigger["attrs"]["aria-expanded"], "false")
        self.assertIn("Mai Nguyễn Nhật Minh", trigger["text"])
        self.assertIn("Chuyên viên Chi cục", trigger["text"])
        self.assertEqual(page.by_class("account-avatar")[0]["text"], "M")
        links = {node["attrs"].get("href") for node in page.by_class("account-menu-item")}
        self.assertTrue({"/profile", "/change-password", "/activity", "/logout"}.issubset(links))
        sidebar = [node for node in page.by_class("sidebar-link") if node["attrs"]["href"] == "/profile"]
        self.assertEqual(len(sidebar), 1)
        self.assertEqual(sidebar[0]["attrs"]["aria-current"], "page")

    def test_missing_or_blank_profile_falls_back_to_username(self):
        for profile in ({}, {"full_name": ""}, {"full_name": "   "}):
            with self.subTest(profile=profile):
                page = Page(self.render(profile))
                self.assertEqual(page.by_class("account-name")[0]["text"], "staff_test")
                self.assertEqual(page.by_class("account-avatar")[0]["text"], "S")

    def test_unusual_names_are_escaped_without_becoming_markup(self):
        for name in (r"Mai \ Nguyễn", '9 <script>alert("name")</script>'):
            page = Page(self.render({"full_name": name}))
            self.assertEqual(page.by_class("account-name")[0]["text"], name)
            self.assertEqual(page.by_class("account-avatar")[0]["text"], name[0].upper())
            scripts = [node for node in page.nodes if node["tag"] == "script" and not node["attrs"].get("src")]
            self.assertEqual(len(scripts), 1)
            self.assertEqual(scripts[0]["attrs"].get("id"), "account-menu-script")

    def test_common_dashboard_has_two_column_desktop_and_one_column_mobile_grids(self):
        css = (Path(server.__file__).parent / "assets" / "app.css").read_text(encoding="utf-8")
        self.assertIn(
            ".dashboard-module-grid{display:grid;grid-template-columns:minmax(0,1fr)",
            css,
        )
        self.assertIn(
            "@media(min-width:1500px){.dashboard-module-grid{grid-template-columns:minmax(0,1.1fr) minmax(0,.9fr)",
            css,
        )
        self.assertIn(
            ".dashboard-stat-grid,.dashboard-summary-grid{display:grid;grid-template-columns:repeat(2",
            css,
        )
        self.assertIn(
            ".dashboard-stat-grid,.dashboard-summary-grid,.dashboard-people{grid-template-columns:minmax(0,1fr)",
            css,
        )

    def test_legacy_unit_header_does_not_offer_personal_profile(self):
        session = {"username": "old_unit", "role": "unit", "unit_name": "Xã cũ"}
        with patch.object(server, "ocop_available", return_value=False):
            self.assertNotIn('href="/profile"', server.base_page("Trang chủ", "", session))


class OcopPresentationTests(unittest.TestCase):
    def page(self, return_context=""):
        page = object.__new__(ocop_pages._Pages)
        page.escape = lambda value, quote=True: escape(str(value or ""), quote=quote)
        page.return_context = return_context
        page.admin = True
        page.scope = None
        page.session = {}
        page.csrf = ""
        return page

    def test_missing_contact_is_rendered_once_without_duplicate_warning(self):
        html = self.page().contact_markup({
            "has_contact": False,
            "representative_name": "",
            "phone": "",
            "email": "",
        })
        self.assertEqual(html.count("Chưa có thông tin liên hệ"), 1)
        self.assertNotIn("Thiếu thông tin liên hệ", html)
        self.assertNotIn("Chưa cập nhật", html)

    def test_contact_markup_only_renders_values_that_exist(self):
        html = self.page().contact_markup({
            "has_contact": True,
            "representative_name": "",
            "phone": "0909000000",
            "email": "",
        })
        self.assertIn("Số điện thoại:", html)
        self.assertIn("0909000000", html)
        self.assertNotIn("Người đại diện:", html)
        self.assertNotIn("Email:", html)
        self.assertNotIn("Chưa cập nhật", html)

    def test_product_detail_uses_whitelisted_back_context_and_formats_dates(self):
        row = {
            "id": 123,
            "status": "active",
            "name": "Sản phẩm thử",
            "ma_san_pham": "SP123",
            "entity_name": "Chủ thể thử",
            "ma_co_so": "CS123",
            "facility_type": "HTX",
            "address": "Địa chỉ thử",
            "representative_name": "Nguyễn Văn A",
            "phone": "0909000000",
            "email": "a@example.com",
            "unit_name": "Xã thử",
            "product_group": "Thực phẩm",
            "recognition_star": 4,
            "latest_recognition_date": "2026-10-27",
            "latest_expiry_date": "2027-01-31",
            "latest_decision_number": "QD-123",
            "latest_decision_authority": "UBND",
            "updated_at": "2026-09-17 08:00:00",
            "created_at": "2026-09-17 07:00:00",
        }
        expiry_html = self.page("expiry").detail_page("products", row)[1]
        self.assertIn('href="/ocop/expiry-alerts"', expiry_html)
        self.assertIn("← Cảnh báo hết hạn", expiry_html)
        self.assertIn("27/10/2026", expiry_html)
        self.assertIn("31/01/2027", expiry_html)
        self.assertIn("Địa chỉ chủ thể", expiry_html)
        self.assertIn("a@example.com", expiry_html)

        catalog_html = self.page("catalog").detail_page("products", row)[1]
        self.assertIn('href="/ocop"', catalog_html)
        self.assertIn("← Tra cứu OCOP", catalog_html)
        arbitrary_html = self.page("https://example.com").detail_page("products", row)[1]
        self.assertIn('href="/ocop"', arbitrary_html)
        self.assertNotIn('href="/ocop/expiry-alerts"', arbitrary_html)


class Client:
    def __init__(self, port):
        self.port, self.cookie, self.csrf = port, "", ""

    def request(self, method, path, data=None):
        headers = {"Cookie": self.cookie}
        body = None
        if data is not None:
            body = urlencode({"csrf": self.csrf, **data})
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            connection.request(method, path, body, headers)
            response = connection.getresponse()
            if response.getheader("Set-Cookie"):
                self.cookie = response.getheader("Set-Cookie").split(";", 1)[0]
            return response.status, dict(response.getheaders()), response.read().decode()
        finally:
            connection.close()

    def login(self, username):
        result = self.request("POST", "/login", {"username": username, "password": "Profile-test-2026"})
        if result[0] != 303:
            raise AssertionError(result)
        status, _, content = self.request("GET", "/profile")
        if status != 200:
            raise AssertionError((status, content))
        self.csrf = Page(content).input("csrf")["value"]
        return self


@unittest.skipUnless(os.getenv("OCOP_TEST_PG_DSN"), "PostgreSQL HTTP tests use disposable databases")
class ProfileHTTPTests(unittest.TestCase):
    connection = profile_tests.UserProfilePostgreSQLTests.connection
    drop_database = profile_tests.UserProfilePostgreSQLTests.drop_database

    def setUp(self):
        profile_tests.UserProfilePostgreSQLTests.setUp(self)
        root = Path(server.__file__).parent
        with self.connection() as con:
            for path in sorted((root / "database/sql").glob("[0-9][0-9][0-9]_*.sql")):
                if path.name[:3] not in ("001", "003"):
                    con.execute(path.read_text(encoding="utf-8"))
            compat = backend_db.CompatConnection(con)
            self.ids = {}
            for username, role in (("profile_admin", "admin"), ("profile_staff", "staff"), ("legacy_unit", "unit")):
                self.ids[username] = server.create_user(compat, username, server.hash_password("Profile-test-2026"), role, user_profiles.CHI_CUC_AGENCY_NAME, server.now_text())
            compat.commit()
        self.patch_connection = patch.object(server, "db_conn", lambda: backend_db.CompatConnection(self.connection()))
        self.patch_connection.start()
        self.addCleanup(self.patch_connection.stop)
        self.patch_sessions = patch.object(server, "SESSIONS", {})
        self.patch_sessions.start()
        self.addCleanup(self.patch_sessions.stop)

        class QuietHandler(app_server.Handler):
            def log_message(self, *args):
                pass

        self.http = server.ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        thread.start()
        def stop():
            self.http.shutdown()
            self.http.server_close()
            thread.join()
        self.addCleanup(stop)
        self.admin = Client(self.http.server_address[1]).login("profile_admin")
        self.staff = Client(self.http.server_address[1]).login("profile_staff")

    def account(self, username):
        with self.connection() as con:
            return dict(con.execute("SELECT * FROM app.users WHERE id=%s", (self.ids[username],)).fetchone())

    def profile(self, username):
        with self.connection() as con:
            return user_profiles.get_profile(backend_db.CompatConnection(con), self.ids[username])

    def test_admin_and_staff_get_own_profile_and_readonly_account_fields(self):
        for client, username in ((self.admin, "profile_admin"), (self.staff, "profile_staff")):
            status, _, content = client.request("GET", "/profile?user_id=" + str(self.ids["legacy_unit"]))
            self.assertEqual(status, 200)
            page = Page(content)
            self.assertEqual(page.by_class("account-name")[0]["text"], username)
            readonly = [node["attrs"]["value"] for node in page.nodes if node["tag"] == "input" and "readonly" in node["attrs"]]
            self.assertIn(username, readonly)
            self.assertIn(server.ROLE_LABELS[self.account(username)["role"]], readonly)
            self.assertIn(user_profiles.CHI_CUC_AGENCY_NAME, readonly)
            self.assertFalse(any(node["tag"] == "input" and node["attrs"].get("name") == "phone" for node in page.nodes))

    def test_profile_post_cannot_change_another_user_or_account_properties(self):
        admin_before = self.profile("profile_admin")
        staff_before = self.account("profile_staff")
        result = self.staff.request("POST", "/profile?user_id=" + str(self.ids["profile_admin"]), {
            "user_id": self.ids["profile_admin"], "id": self.ids["profile_admin"],
            "full_name": "Nhân viên kiểm thử", "department": user_profiles.STAFF_DEPARTMENTS[0],
            "role": "admin", "username": "forged", "agency_name": "Cơ quan giả", "unit_name": "Giả",
        })
        self.assertEqual(result[0], 303)
        self.assertEqual(self.profile("profile_admin"), admin_before)
        self.assertEqual(self.account("profile_staff"), staff_before)
        self.assertEqual(self.profile("profile_staff")["agency_name"], user_profiles.CHI_CUC_AGENCY_NAME)
        self.assertEqual(self.profile("profile_staff")["full_name"], "Nhân viên kiểm thử")
        self.assertEqual(self.staff.request("GET", f'/users/{self.ids["profile_admin"]}/edit')[0], 403)

    def test_unknown_staff_department_is_rejected_server_side(self):
        before = self.profile("profile_staff")
        status, _, content = self.staff.request("POST", "/profile", {
            "full_name": "Nhân viên kiểm thử", "department": "Phòng tự nhập", "official_email": "a@example.gov.vn",
        })
        self.assertEqual(status, 400)
        self.assertIn("Phòng/Bộ phận", content)
        self.assertEqual(self.profile("profile_staff"), before)

    def test_admin_and_self_edits_share_the_same_profile_in_both_directions(self):
        uid = self.ids["profile_staff"]
        dept_a, dept_b = user_profiles.STAFF_DEPARTMENTS
        self.assertEqual(self.admin.request("POST", f"/users/{uid}/edit", {
            "username": "profile_staff", "role": "staff", "active": "1", "password": "",
            "full_name": "Nguyễn Văn A", "job_title": "Chuyên viên", "department": dept_a,
            "official_email": "a@example.gov.vn", "unit_name": "Giả",
        })[0], 303)
        self.staff.login("profile_staff")
        page = Page(self.staff.request("GET", "/profile")[2])
        self.assertEqual(page.by_class("account-name")[0]["text"], "Nguyễn Văn A")
        self.assertEqual(page.input("full_name")["value"], "Nguyễn Văn A")
        self.assertEqual(page.selected_option("department"), dept_a)
        self.assertEqual(self.staff.request("POST", "/profile", {
            "full_name": "Nguyễn Văn A", "department": dept_b, "job_title": "Phó trưởng phòng",
            "official_email": "a@example.gov.vn",
        })[0], 303)
        page = Page(self.admin.request("GET", f"/users/{uid}/edit")[2])
        self.assertEqual(page.selected_option("department"), dept_b)
        self.assertEqual(page.input("job_title")["value"], "Phó trưởng phòng")
        self.assertEqual(self.admin.request("POST", f"/users/{uid}/edit", {"username":"profile_staff", "role":"staff", "active":"1"})[0], 303)
        self.assertEqual(self.profile("profile_staff")["department"], dept_b)

    def test_phone_value_is_preserved_but_no_longer_editable(self):
        with self.connection() as con:
            con.execute(
                """INSERT INTO app.user_profiles(user_id,phone,agency_name)
                   VALUES(%s,'0901234567',%s)
                   ON CONFLICT(user_id) DO UPDATE SET phone=EXCLUDED.phone""",
                (self.ids["profile_staff"], user_profiles.CHI_CUC_AGENCY_NAME),
            )
        self.assertEqual(self.staff.request("POST", "/profile", {
            "full_name": "Nhân viên", "department": user_profiles.STAFF_DEPARTMENTS[0], "official_email": "nv@example.gov.vn",
        })[0], 303)
        self.assertEqual(self.profile("profile_staff")["phone"], "0901234567")
        self.assertNotIn('name="phone"', self.staff.request("GET", "/profile")[2])

    def test_account_creation_and_profile_validation_are_atomic(self):
        data = {"username":"new_staff", "password":"Profile-test-2026", "role":"staff", "full_name":"Mai Nguyễn Nhật Minh", "department":user_profiles.STAFF_DEPARTMENTS[0], "official_email":"bad-email"}
        self.assertEqual(self.admin.request("POST", "/users/new", data)[0], 400)
        with self.connection() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM app.users WHERE username='new_staff'").fetchone()[0], 0)
        self.assertEqual(self.admin.request("POST", "/users/new", {**data, "official_email":"minh@example.gov.vn"})[0], 303)
        client = Client(self.http.server_address[1]).login("new_staff")
        self.assertEqual(Page(client.request("GET", "/profile")[2]).by_class("account-name")[0]["text"], data["full_name"])
        self.assertEqual(self.admin.request("POST", "/users/new", {
            "username":"missing_department", "password":"Profile-test-2026", "role":"staff", "full_name":"Thiếu phòng"
        })[0], 400)
        with self.connection() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM app.users WHERE username='missing_department'").fetchone()[0], 0)
        before = self.account("profile_staff")
        self.assertEqual(self.admin.request("POST", f'/users/{self.ids["profile_staff"]}/edit', {
            "username":"must_rollback", "role":"staff", "active":"1", "full_name":"A", "department":user_profiles.STAFF_DEPARTMENTS[0], "official_email":"invalid",
        })[0], 400)
        self.assertEqual(self.account("profile_staff"), before)

    def test_activity_page_is_scoped_for_staff_and_admin_can_see_all(self):
        self.assertEqual(self.staff.request("POST", "/profile", {
            "full_name": "Nhân viên A", "department": user_profiles.STAFF_DEPARTMENTS[0], "official_email": "a@example.gov.vn",
        })[0], 303)
        status, _, content = self.staff.request("GET", "/activity")
        self.assertEqual(status, 200)
        self.assertIn("Cập nhật thông tin cá nhân", content)
        self.assertIn("Nhân viên A", content)
        self.assertNotIn("profile_admin", content)
        status, _, admin_content = self.admin.request("GET", "/activity")
        self.assertEqual(status, 200)
        self.assertIn("Nhân viên A", admin_content)
        self.assertIn("Tất cả người dùng", admin_content)

    def test_csrf_logout_and_legacy_unit_policy_remain_enforced(self):
        before = self.profile("profile_staff")
        self.assertEqual(self.staff.request("POST", "/profile", {"csrf":"invalid", "full_name":"A"})[0], 400)
        self.assertEqual(self.profile("profile_staff"), before)
        legacy = Client(self.http.server_address[1])
        self.assertNotEqual(legacy.request("POST", "/login", {"username":"legacy_unit", "password":"Profile-test-2026"})[0], 303)
        with self.connection() as con:
            row = server.get_user(backend_db.CompatConnection(con), self.ids["legacy_unit"])
            sid = server.new_session(row)
        legacy.cookie = "salt_session=" + sid
        self.assertEqual(legacy.request("GET", "/profile")[0], 403)
        self.assertEqual(legacy.request("POST", "/profile", {"full_name":"Không được sửa"})[0], 403)
        self.assertEqual(self.admin.request("POST", "/users/new", {"username":"new_unit", "password":"Profile-test-2026", "role":"unit"})[0], 400)
        self.assertEqual(self.staff.request("GET", "/logout")[0], 303)
        self.assertEqual(self.staff.request("GET", "/profile")[0], 303)

    def test_existing_business_routes_keep_working_with_account_menu(self):
        for path in ("/dashboard", "/records", "/import-excel", "/ocop", "/ocop/import"):
            with self.subTest(path=path):
                status, _, content = self.staff.request("GET", path)
                self.assertEqual(status, 200)
                self.assertEqual(len(Page(content).by_class("account-menu-trigger")), 1)
                self.assertIn('href="/activity"', content)

    def test_common_dashboard_renders_both_modules_and_responsive_grids(self):
        status, _, content = self.staff.request("GET", "/dashboard")
        self.assertEqual(status, 200)
        self.assertIn("Bảng giám sát", content)
        self.assertIn('aria-labelledby="salt-dashboard-title"', content)
        self.assertIn('aria-labelledby="ocop-dashboard-title"', content)
        self.assertIn("dashboard-stat-grid", content)
        self.assertIn("dashboard-summary-grid", content)
        self.assertIn('class="dashboard-module-grid"', content)
        self.assertNotIn("PHÂN HỆ 01", content)
        self.assertNotIn("PHÂN HỆ 02", content)
        self.assertIn("Tính đến ngày", content)
        self.assertNotIn("Cập nhật ngày", content)
        self.assertNotIn("breakdown lấy từ dữ liệu đã tổng hợp", content)
        self.assertNotIn("recognition hiện hành và phạm vi địa bàn đang chọn", content)
        self.assertNotIn('class="dashboard-stat-card warning"', content)
        self.assertIn("Xem chi tiết Diêm nghiệp", content)
        self.assertIn("Xem chi tiết OCOP", content)
        self.assertIn("Đặt lại bộ lọc", content)
        self.assertIn("dashboard-v1", content)
