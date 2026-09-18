"""Login presentation checks against the real HTTP handler, without a database."""
from __future__ import annotations

import os
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse


@unittest.skipUnless(os.getenv("OCOP_TEST_BROWSER"), "Runs in Chromium browser CI")
class LoginVisualBrowserTests(unittest.TestCase):
    def setUp(self):
        # Use the launcher's real login bootstrap, without running startup or
        # opening the configured production database. Snapshot hooks before any
        # bootstrap work so discovery order cannot change subsequent tests.
        import runpy
        import sys
        import server

        original_login = server.login_page
        handler = server.Handler
        missing = object()
        original_redirect = handler.__dict__.get("redirect", missing)

        def restore_hooks():
            server.login_page = original_login
            if original_redirect is missing:
                if "redirect" in handler.__dict__:
                    delattr(handler, "redirect")
            else:
                handler.redirect = original_redirect

        self.addCleanup(restore_hooks)
        cached_bootstrap = sys.modules.get("sitecustomize")
        if (cached_bootstrap is None
                or getattr(cached_bootstrap, "_core", None) is not server
                or server.login_page is not getattr(cached_bootstrap, "_v11_login_page", None)):
            # Python can cache a failed early sitecustomize import before
            # unittest adds the checkout to sys.path. Execute the same file in
            # fresh globals without mutating that cache or retaining test hooks.
            bootstrap = runpy.run_path(str(Path(__file__).resolve().parents[1] / "sitecustomize.py"))
            self.assertIs(bootstrap.get("_core"), server, "The v1.1 login bootstrap did not initialize")

        import app_server
        from playwright.sync_api import sync_playwright

        self.core = server
        db_patch = patch.object(server, "db_conn", side_effect=AssertionError("Login visual tests must not access a database"))
        self.db_guard = db_patch.start()
        self.addCleanup(self.db_guard.assert_not_called)
        self.addCleanup(db_patch.stop)
        sessions_patch = patch.object(server, "SESSIONS", {})
        sessions_patch.start()
        self.addCleanup(sessions_patch.stop)

        class QuietHandler(app_server.Handler):
            def log_message(self, *args):
                pass

        self.http = server.ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.origin = f"http://127.0.0.1:{self.http.server_address[1]}"
        self.playwright = sync_playwright().start()
        self.addCleanup(self.playwright.stop)
        options = {"headless": True}
        if os.getenv("LOGIN_BROWSER_EXECUTABLE"):
            options["executable_path"] = os.environ["LOGIN_BROWSER_EXECUTABLE"]
        self.browser = self.playwright.chromium.launch(**options)
        self.addCleanup(self.browser.close)

    def stop_server(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=5)

    def new_page(self, width=1440, height=900):
        context = self.browser.new_context(viewport={"width": width, "height": height})
        self.addCleanup(context.close)
        page = context.new_page()
        page.goto(self.origin + "/login", wait_until="networkidle")
        return context, page

    def assert_form_contract(self, page):
        from playwright.sync_api import expect

        form = page.locator("#login-v11-form")
        expect(form).to_have_attribute("method", "post")
        expect(form).to_have_attribute("action", "/login")
        expect(form.locator('[name="username"]')).to_have_attribute("autocomplete", "username")
        expect(form.locator('[name="password"]')).to_have_attribute("type", "password")
        expect(form.locator('[name="password"]')).to_have_attribute("autocomplete", "current-password")
        expect(form.locator('[name="remember"]')).to_have_attribute("type", "checkbox")
        expect(form.locator('[name="remember"]')).to_have_attribute("value", "1")
        self.assertTrue(form.locator('[name="username"]').evaluate("el => el.required"))
        self.assertTrue(form.locator('[name="password"]').evaluate("el => el.required"))
        expect(form.get_by_role("button", name="Đăng nhập")).to_be_visible()

    def test_real_hero_loads_and_login_remains_usable_at_requested_viewports(self):
        from playwright.sync_api import expect

        for width, height in ((1920, 1080), (1440, 900), (390, 844)):
            with self.subTest(viewport=f"{width}x{height}"):
                context, page = self.new_page(width, height)
                self.assert_form_contract(page)
                expect(page.locator(".login-v11-card")).to_be_visible()
                page.wait_for_function("document.documentElement.scrollWidth <= innerWidth")
                card = page.locator(".login-v11-card").bounding_box()
                self.assertIsNotNone(card)
                self.assertGreaterEqual(card["x"], 0)
                self.assertLessEqual(card["x"] + card["width"], width + 1)
                self.assertGreater(card["width"], 280)

                hero = page.locator(".login-v11-visual img")
                expect(hero).to_have_count(1)
                expect(hero).to_be_visible()
                hero.evaluate("image => image.decode()")
                image = hero.evaluate("""image => ({
                    src: image.currentSrc,
                    width: image.naturalWidth,
                    height: image.naturalHeight,
                    fit: getComputedStyle(image).objectFit
                })""")
                self.assertGreater(image["width"], 0)
                self.assertGreater(image["height"], 0)
                # Cover scales the artwork uniformly and crops the edges rather
                # than stretching the seal with independent width/height scales.
                self.assertEqual(image["fit"], "cover")
                self.assertEqual(urlparse(image["src"]).path, "/assets/login-hero.png")
                asset = context.request.get(image["src"])
                self.assertEqual(asset.status, 200)
                self.assertTrue(asset.headers.get("content-type", "").startswith("image/"))
                visual = page.locator(".login-v11-visual").bounding_box()
                if width > 760:
                    self.assertGreaterEqual(visual["width"] / width, 0.50)
                    self.assertLessEqual(visual["width"] / width, 0.52)
                    self.assertGreaterEqual(card["x"], visual["x"] + visual["width"])
                    self.assertGreaterEqual(card["y"], 0)
                    self.assertLessEqual(card["y"] + card["height"], height + 1)

                screenshot_dir = os.getenv("LOGIN_SCREENSHOT_DIR")
                if screenshot_dir:
                    target = Path(screenshot_dir)
                    target.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(target / f"login-{width}x{height}.png"), full_page=True)
                context.close()

    def test_remember_keeps_only_username_and_uncheck_clears_it(self):
        from playwright.sync_api import expect
        from login_theme import REMEMBER_SECONDS

        context, page = self.new_page()
        submitted = []

        def intercept_login(route):
            if route.request.method != "POST":
                route.continue_()
                return
            submitted.append(parse_qs(route.request.post_data or ""))
            # Exercise the existing submit script and browser navigation while
            # deliberately keeping dummy credentials away from any database.
            route.fulfill(status=200, content_type="text/html; charset=utf-8", body=self.core.login_page())

        context.route("**/login", intercept_login)
        dummy_username = "visual_only_account"
        dummy_password = "Visual-only-password-2026"
        page.locator('[name="username"]').fill(dummy_username)
        page.locator('[name="password"]').fill(dummy_password)
        page.locator('[name="remember"]').check()
        with page.expect_navigation(wait_until="load"):
            page.locator("#login-v11-form").get_by_role("button", name="Đăng nhập").click()
        self.assertEqual(submitted, [{"username": [dummy_username], "password": [dummy_password], "remember": ["1"]}])
        page.reload(wait_until="networkidle")
        expect(page.locator('[name="username"]')).to_have_value(dummy_username)
        expect(page.locator('[name="remember"]')).to_be_checked()
        expect(page.locator('[name="password"]')).to_have_value("")
        storage = page.evaluate("() => ({local: {...localStorage}, session: {...sessionStorage}})")
        self.assertEqual(storage["local"].get("salt-login-username"), dummy_username)
        self.assertNotIn(dummy_password, str(storage))
        self.assertFalse(any("password" in key.lower() for values in storage.values() for key in values))
        cookies = context.cookies()
        remembered = next(cookie for cookie in cookies if cookie["name"] == "remember_login")
        self.assertEqual(remembered["value"], "1")
        self.assertAlmostEqual(remembered["expires"] - time.time(), REMEMBER_SECONDS, delta=15)
        self.assertFalse(any(dummy_password in cookie["value"] for cookie in cookies))

        page.locator('[name="remember"]').uncheck()
        page.locator('[name="password"]').fill(dummy_password)
        with page.expect_navigation(wait_until="load"):
            page.locator("#login-v11-form").get_by_role("button", name="Đăng nhập").click()
        self.assertEqual(submitted[-1], {"username": [dummy_username], "password": [dummy_password]})
        page.reload(wait_until="networkidle")
        expect(page.locator('[name="username"]')).to_have_value("")
        expect(page.locator('[name="remember"]')).not_to_be_checked()
        expect(page.locator('[name="password"]')).to_have_value("")
        self.assertIsNone(page.evaluate("localStorage.getItem('salt-login-username')"))
        self.assertFalse(any(cookie["name"] == "remember_login" for cookie in context.cookies()))

    def test_login_error_remains_escaped_and_form_usable_on_mobile(self):
        from playwright.sync_api import expect

        original_login_page = self.core.login_page
        message = "Tên đăng nhập hoặc mật khẩu không đúng. <script>window.loginUnsafe = true</script>"
        with patch.object(self.core, "login_page", side_effect=lambda *_: original_login_page(message)):
            _, page = self.new_page(390, 844)
            expect(page.get_by_role("alert")).to_have_text(message)
            self.assertIsNone(page.evaluate("window.loginUnsafe"))
            self.assert_form_contract(page)
            self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
            page.locator('[name="username"]').fill("visual_retry")
            expect(page.locator('[name="username"]')).to_have_value("visual_retry")


if __name__ == "__main__":
    unittest.main()
