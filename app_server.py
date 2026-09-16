"""Application entry point that composes the existing server with user profiles.

There is still a single HTTP server and a single PostgreSQL database. The
existing ``server.py`` remains the business core; this module adds the profile
route and shell decoration without duplicating salt/OCOP handlers.
"""
from __future__ import annotations

import logging
from urllib.parse import urlparse

import server as core
import user_profiles


CoreHandler = core.Handler


class Handler(CoreHandler):
    def _profile_session(self):
        try:
            _, session = core.get_session(self)
            return session
        except Exception:
            return None

    def _load_profile(self, session):
        con = core.db_conn()
        try:
            return user_profiles.get_profile(con, session["user_id"])
        finally:
            con.close()

    def send_html(self, content, status=200, extra_headers=None):
        session = self._profile_session()
        if session and core.is_chi_cuc_user(session):
            try:
                content = user_profiles.enhance_shell(
                    content, session, self._load_profile(session), core.icon
                )
            except Exception:
                # A profile rendering problem must never hide the business page.
                logging.exception("Could not decorate page with user profile")
        return super().send_html(content, status, extra_headers)

    def do_GET(self):
        path = urlparse(self.path).path
        if path != "/profile":
            return super().do_GET()

        _, session = self.require_session()
        if not session:
            return
        if not core.is_chi_cuc_user(session):
            self.send_html(
                core.base_page(
                    "403",
                    '<div class="container"><div class="notice err">Chỉ tài khoản nội bộ Chi cục được sử dụng hồ sơ cá nhân.</div></div>',
                    session,
                ),
                403,
            )
            return
        profile = self._load_profile(session)
        body = user_profiles.profile_body(
            session,
            profile,
            core.csrf_input(session),
            core.ROLE_LABELS[session["role"]],
        )
        flash = core.take_flash(session)
        if flash:
            body = body.replace('<div class="container profile-page">', '<div class="container profile-page">' + flash, 1)
        self.send_html(core.base_page("Thông tin cá nhân", body, session, active_path="/profile"))

    def do_POST(self):
        path = urlparse(self.path).path
        if path != "/profile":
            return super().do_POST()

        _, session = self.require_session()
        if not session:
            return
        if not core.is_chi_cuc_user(session):
            self.send_html(
                core.base_page(
                    "403",
                    '<div class="container"><div class="notice err">Không có quyền cập nhật hồ sơ cá nhân.</div></div>',
                    session,
                ),
                403,
            )
            return
        data = core.parse_body(self)
        if not core.check_csrf(session, data):
            self.send_html(
                core.base_page(
                    "Lỗi",
                    '<div class="container"><div class="notice err">Phiên làm việc không hợp lệ. Vui lòng tải lại trang.</div></div>',
                    session,
                ),
                400,
            )
            return

        con = core.db_conn()
        try:
            con.execute("BEGIN")
            user_profiles.save_profile(con, session["user_id"], data)
            con.commit()
        except user_profiles.ProfileError as exc:
            con.rollback()
            profile = user_profiles.get_profile(con, session["user_id"])
            for field in user_profiles.PROFILE_FIELDS:
                if field in data:
                    profile[field] = data[field]
            form = user_profiles.profile_body(
                session,
                profile,
                core.csrf_input(session),
                core.ROLE_LABELS[session["role"]],
            )
            form = form.replace(
                '<div class="container profile-page">',
                f'<div class="container profile-page"><div class="notice err">{core.esc(exc)}</div>',
                1,
            )
            self.send_html(core.base_page("Thông tin cá nhân", form, session, active_path="/profile"), 400)
            return
        except Exception:
            con.rollback()
            logging.exception("Could not save user profile")
            self.send_html(
                core.base_page(
                    "Thông tin cá nhân",
                    '<div class="container"><div class="notice err">Không thể lưu thông tin cá nhân lúc này.</div></div>',
                    session,
                    active_path="/profile",
                ),
                500,
            )
            return
        finally:
            con.close()

        core.set_flash(session, "ok", "Đã cập nhật thông tin cá nhân.")
        self.redirect("/profile")


# server.main() resolves Handler from its module globals when it starts the
# HTTP server, so replacing this single reference keeps all existing routes.
core.Handler = Handler


if __name__ == "__main__":
    core.main()
