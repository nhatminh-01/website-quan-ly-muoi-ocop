"""Browser interaction/layout checks on a disposable PostgreSQL fixture."""
import os
import unittest

import test_profile_http as fixtures


@unittest.skipUnless(os.getenv("OCOP_TEST_BROWSER") and os.getenv("OCOP_TEST_PG_DSN"), "Runs in PostgreSQL browser CI")
class ManualBrowserTests(unittest.TestCase):
    connection = fixtures.ProfileHTTPTests.connection
    drop_database = fixtures.ProfileHTTPTests.drop_database
    setUp = fixtures.ProfileHTTPTests.setUp

    def test_multiple_recognitions_submit_and_responsive_layout(self):
        from playwright.sync_api import sync_playwright, expect, TimeoutError as BrowserTimeout
        origin = f"http://127.0.0.1:{self.http.server_address[1]}"
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = browser.new_context(viewport={"width":1366, "height":900})
                name, value = self.staff.cookie.split("=", 1)
                context.add_cookies([{"name":name, "value":value, "url":origin}])
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(origin + "/ocop/manual")
                self.assertEqual(page.request.get(origin + "/assets/ocop-manual.js").status, 200)

                menu_labels = page.locator('.sidebar-group[data-group="ocop"] .sidebar-group-links .sidebar-label').all_text_contents()
                self.assertEqual([text.strip() for text in menu_labels], [
                    "Tra cứu / Xuất báo cáo",
                    "Nhập dữ liệu",
                    "Cảnh báo hết hạn",
                ])
                menu_entry = page.locator('.sidebar-group[data-group="ocop"] a', has_text="Nhập dữ liệu")
                expect(menu_entry).to_have_attribute("href", "/ocop/manual")
                expect(menu_entry).to_have_class(lambda value: "active" in value.split())
                self.assertEqual(page.locator('[aria-label="Phương thức nhập dữ liệu OCOP"]').count(), 0)

                excel_button = page.get_by_role("link", name="Nhập bằng file Excel", exact=True)
                expect(excel_button).to_have_attribute("href", "/ocop/import")
                self.assertEqual(excel_button.evaluate("el => getComputedStyle(el).backgroundColor"), "rgb(37, 99, 235)")
                self.assertEqual(page.locator('.sidebar-footer p').inner_text().strip(), "v.1.0")

                page.locator('[name="entity_name"]').fill("Hợp tác xã trình duyệt")
                page.locator('[name="business_type"]').select_option("Hợp tác xã")
                page.locator('[name="unit_code"]').select_option("27595")
                page.locator('[name="product_name"]').fill("Sản phẩm trình duyệt")
                page.locator('[name="product_group"]').select_option("Gia vị")
                page.locator('[name="recognition_0_star_rank"]').select_option("3")
                page.locator('[name="recognition_0_evaluation_type"]').select_option("new")
                page.locator('[name="recognition_0_recognition_year"]').fill("2025")
                page.locator('[data-add-recognition]').click()
                expect(page.locator('[data-recognition]')).to_have_count(2)
                page.locator('[name="recognition_1_star_rank"]').select_option("4")
                page.locator('[name="recognition_1_evaluation_type"]').select_option("upgrade")
                page.locator('[name="recognition_1_recognition_year"]').fill("2026")
                page.locator('[data-add-recognition]').click()
                page.locator('[data-remove-recognition]').last.click()
                expect(page.locator('[data-recognition]')).to_have_count(2)
                for width in (1366, 760, 390, 320):
                    page.set_viewport_size({"width":width, "height":900})
                    # The existing sidebar animates main margin on breakpoint
                    # changes. Check the settled layout, not that transition.
                    try:
                        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth", timeout=5000)
                    except BrowserTimeout:
                        pass  # The assertion below reports the overflowing nodes.
                    overflow = page.evaluate("""() => [...document.querySelectorAll('body *')]
                      .filter(e => e.getBoundingClientRect().right > innerWidth + 1)
                      .map(e => ({tag:e.tagName, cls:e.className, right:e.getBoundingClientRect().right})).slice(0,12)""")
                    self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"), f"viewport={width}: {overflow}")
                    self.assertEqual(page.locator('[name="recognition_1_star_rank"]').input_value(), "4")
                page.get_by_role("button", name="Lưu dữ liệu", exact=True).click()
                expect(page.get_by_role("status")).to_have_text("Đã lưu dữ liệu OCOP thành công.")
                expect(page.get_by_role("link", name="Nhập bằng file Excel", exact=True)).to_have_attribute("href", "/ocop/import")
                page.get_by_role("link", name="Xem sản phẩm", exact=True).click()
                expect(page.locator(".ocop-page")).to_contain_text("4 sao")
                self.assertEqual(errors, [])
                context.close()
            finally:
                browser.close()
