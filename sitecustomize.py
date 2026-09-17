"""Application bootstrap hooks loaded automatically by Python's site module."""
from __future__ import annotations

try:
    import server as _core
    import login_theme_runtime as _login_theme
except Exception:  # pragma: no cover
    _core = None
    _login_theme = None

if _core is not None and _login_theme is not None:
    _original_login_page = _core.login_page
    _original_redirect = _core.Handler.redirect

    def _v11_login_page(message=""):
        return _login_theme.enhance_login_page(_original_login_page(message))

    def _v11_redirect(self, location, extra_headers=None):
        headers = list(extra_headers or [])
        if location == "/dashboard" and getattr(self, "path", "").split("?", 1)[0] == "/login":
            remember = _login_theme.remember_cookie_enabled(self.headers.get("Cookie", ""))
            headers = [
                (name, _login_theme.extend_session_cookie(value, remember) if name.lower() == "set-cookie" else value)
                for name, value in headers
            ]
        return _original_redirect(self, location, headers)

    _core.login_page = _v11_login_page
    _core.Handler.redirect = _v11_redirect
