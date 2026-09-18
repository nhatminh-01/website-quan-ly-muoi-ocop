import unittest

import login_theme_runtime as theme


class LoginV11ThemeTests(unittest.TestCase):
    def test_replaces_legacy_login_and_keeps_error(self):
        legacy = '''<html><body><div class="login-wrap"><div class="login">
        <img class="login-emblem"><h1>Hệ thống quản lý nghiệp vụ</h1><p>Nội dung cũ</p>
        <div class="notice err">Sai mật khẩu.</div>
        <form method="post" action="/login"><div class="field"></div></form>
        <div class="notice info">Thông tin cũ</div></div></div></body></html>'''
        page = theme.enhance_login_page(legacy)
        self.assertIn('login-v11-shell', page)
        self.assertIn('Trung tâm Chuyển đổi số Nông nghiệp và Môi trường', page)
        self.assertIn('name="remember" value="1"', page)
        self.assertIn('login-v11-password-toggle', page)
        self.assertIn('aria-label="Hiển thị mật khẩu"', page)
        self.assertIn('login-v11-contact', page)
        self.assertIn('Chi cục Phát triển nông thôn TP. Hồ Chí Minh', page)
        self.assertIn('56 58 Bạch Đằng, Phường Bình Thạnh, Thành phố Hồ Chí Minh', page)
        self.assertIn('linear-gradient(90deg', page)
        self.assertIn('028 3822 6793', page)
        self.assertIn('ccptnt.snnmt@tphcm.gov.vn', page)
        self.assertIn('http://ccptnt.vn', page)
        self.assertIn('Sai mật khẩu.', page)
        self.assertNotIn('Nội dung cũ', page)
        self.assertNotIn('NÔNG THÔN PHÁT TRIỂN - NÔNG NGHIỆP BỀN VỮNG', page.upper())

    def test_remember_cookie_is_extended_for_thirty_days(self):
        plain = 'salt_session=abc; Path=/; HttpOnly; SameSite=Lax'
        remembered = theme.extend_session_cookie(plain, True)
        self.assertIn(f'Max-Age={theme.REMEMBER_SECONDS}', remembered)
        self.assertEqual(theme.extend_session_cookie(plain, False), plain)
        self.assertTrue(theme.remember_cookie_enabled('foo=1; remember_login=1'))
        self.assertFalse(theme.remember_cookie_enabled('foo=1'))


if __name__ == '__main__':
    unittest.main()
