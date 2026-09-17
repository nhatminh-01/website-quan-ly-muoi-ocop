"""OCOP v1.1 data-entry hub: menu, route, permissions, links and responsive layout."""
import os
import unittest

import app_server
import backend_db
import server
import test_profile_http as fixtures


def ocop_sidebar_links(content):
    page = fixtures.Page(content)
    result = []
    for node in page.nodes:
        if node["tag"] != "a" or "sidebar-link" not in node["attrs"].get("class", "").split():
            continue
        inside_ocop = any(
            parent["tag"] == "details" and parent["attrs"].get("data-group") == "ocop"
            for parent in node["parents"]
        )
        if inside_ocop:
            result.append((node["attrs"].get("href"), node["text"].strip(), node["attrs"]))
    return result


class DataEntryMarkupTests(unittest.TestCase):
    def test_choice_page_declares_two_column_desktop_and_one_column_mobile(self):
        html = app_server.ocop_data_entry_body()
        self.assertEqual(html.count('class="card ocop-entry-card"'), 2)
        self.assertIn("grid-template-columns:repeat(2,minmax(0,1fr))", html)
        self.assertIn("@media(max-width:760px)", html)
        self.assertIn("grid-template-columns:minmax(0,1fr)", html)
        self.assertIn('href="/ocop/import"', html)
        self.assertIn('href="/ocop/manual"', html)


@unittest.skipUnless(os.getenv("OCOP_TEST_PG_DSN"), "Requires disposable PostgreSQL test databases")
class DataEntryHTTPTests(unittest.TestCase):
    connection = fixtures.ProfileHTTPTests.connection
    drop_database = fixtures.ProfileHTTPTests.drop_database

    def setUp(self):
        fixtures.ProfileHTTPTests.setUp(self)

    def legacy_client(self):
        con = backend_db.CompatConnection(self.connection())
        try:
            row = server.get_user(con, self.ids["legacy_unit"])
        finally:
            con.close()
        sid = server.new_session(row)
        client = fixtures.Client(self.http.server_address[1])
        client.cookie = "salt_session=" + sid
        client.csrf = server.SESSIONS[sid]["csrf"]
        return client

    def test_sidebar_has_single_data_entry_item_in_required_order(self):
        for client in (self.admin, self.staff):
            status, _, content = client.request("GET", "/ocop/data-entry")
            self.assertEqual(status, 200)
            links = ocop_sidebar_links(content)
            self.assertEqual([item[0] for item in links], [
                "/ocop",
                "/ocop/data-entry",
                "/ocop/expiry-alerts",
            ])
            self.assertEqual([item[1] for item in links], [
                "Tra cứu / Xuất báo cáo",
                "Nhập dữ liệu",
                "Cảnh báo hết hạn",
            ])
            self.assertIn("active", links[1][2].get("class", "").split())
            self.assertEqual(links[1][2].get("aria-current"), "page")
            self.assertNotIn('href="/ocop/import" title="Import dữ liệu OCOP"', content)
            self.assertNotIn('href="/ocop/manual" title="Nhập dữ liệu trực tiếp"', content)

    def test_choice_page_cards_link_to_existing_methods(self):
        status, _, content = self.staff.request("GET", "/ocop/data-entry")
        self.assertEqual(status, 200)
        self.assertIn("Import file Excel", content)
        self.assertIn("Nhập dữ liệu trực tiếp", content)
        self.assertIn('href="/ocop/import"', content)
        self.assertIn('href="/ocop/manual"', content)
        self.assertEqual(content.count('class="card ocop-entry-card"'), 2)

    def test_import_and_manual_have_back_link_and_data_entry_stays_active(self):
        for path in ("/ocop/import", "/ocop/manual"):
            status, _, content = self.staff.request("GET", path)
            self.assertEqual(status, 200)
            self.assertIn('href="/ocop/data-entry"', content)
            links = ocop_sidebar_links(content)
            data_entry = next(item for item in links if item[0] == "/ocop/data-entry")
            self.assertIn("active", data_entry[2].get("class", "").split())
            self.assertEqual(data_entry[2].get("aria-current"), "page")

    def test_legacy_unit_is_forbidden_from_data_entry_hub(self):
        legacy = self.legacy_client()
        status, _, content = legacy.request("GET", "/ocop/data-entry")
        self.assertEqual(status, 403)
        self.assertIn("Chỉ tài khoản nội bộ Chi cục", content)


@unittest.skipUnless(
    os.getenv("OCOP_TEST_BROWSER") and os.getenv("OCOP_TEST_PG_DSN"),
    "Runs in PostgreSQL browser CI",
)
class DataEntryBrowserTests(unittest.TestCase):
    connection = fixtures.ProfileHTTPTests.connection
    drop_database = fixtures.ProfileHTTPTests.drop_database

    def setUp(self):
        fixtures.ProfileHTTPTests.setUp(self)

    def test_cards_are_equal_height_on_desktop_and_stack_on_mobile(self):
        from playwright.sync_api import sync_playwright, expect

        origin = f"http://127.0.0.1:{self.http.server_address[1]}"
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = browser.new_context(viewport={"width": 1366, "height": 900})
                name, value = self.staff.cookie.split("=", 1)
                context.add_cookies([{"name": name, "value": value, "url": origin}])
                page = context.new_page()
                page.goto(origin + "/ocop/data-entry")
                cards = page.locator(".ocop-entry-card")
                expect(cards).to_have_count(2)

                first = cards.nth(0).bounding_box()
                second = cards.nth(1).bounding_box()
                self.assertIsNotNone(first)
                self.assertIsNotNone(second)
                self.assertLess(abs(first["y"] - second["y"]), 2)
                self.assertLess(abs(first["height"] - second["height"]), 2)
                self.assertGreater(second["x"], first["x"])

                page.set_viewport_size({"width": 390, "height": 900})
                page.wait_for_function("document.documentElement.scrollWidth <= innerWidth")
                first = cards.nth(0).bounding_box()
                second = cards.nth(1).bounding_box()
                self.assertGreaterEqual(second["y"], first["y"] + first["height"])
                self.assertLess(abs(first["x"] - second["x"]), 2)
                self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
                context.close()
            finally:
                browser.close()
