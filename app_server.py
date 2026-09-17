"""Application entry point that composes the existing server with profiles/activity.

There is still a single HTTP server and a single PostgreSQL database. The
existing ``server.py`` remains the business core; this module adds personal
profiles, the account dropdown and activity history without duplicating the
salt/OCOP business handlers.
"""
from __future__ import annotations

import logging
from urllib.parse import urlparse

import server as core
import user_profiles
import activity_log


# Existing record mutations already call server.add_audit. Replacing the global
# function keeps those call sites intact while enriching new rows with user
# snapshots and module metadata.
core.add_audit = activity_log.add_record_audit
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

    def _audit_meta(self):
        ip_address = ""
        try:
            ip_address = self.client_address[0]
        except Exception:
            pass
        return ip_address, self.headers.get("User-Agent", "")

    def _write_activity(self, session, module, action, detail, *, success=True):
        if not session or not core.is_chi_cuc_user(session):
            return
        con = None
        try:
            con = core.db_conn()
            ip_address, user_agent = self._audit_meta()
            activity_log.write_activity(
                con,
                session["user_id"],
                action,
                detail,
                module=module,
                success=success,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            con.commit()
        except Exception:
            if con is not None:
                try:
                    con.rollback()
                except Exception:
                    pass
            logging.exception("Could not append activity audit")
        finally:
            if con is not None:
                con.close()

    def send_response(self, code, message=None):
        self._activity_response_status = code
        return super().send_response(code, message)

    def send_html(self, content, status=200, extra_headers=None):
        content = content.replace(
            '<p>Theo dõi sản xuất và tổng hợp báo cáo các đơn vị.</p>',
            '<p>v1.0</p>',
        ).replace(
            '<p>Quản lý tập trung dữ liệu Diêm nghiệp và OCOP.</p>',
            '<p>v1.0</p>',
        )
        session = self._profile_session()
        if session and core.is_chi_cuc_user(session):
            try:
                content = user_profiles.enhance_shell(
                    content, session, self._load_profile(session), core.icon
                )
            except Exception:
                logging.exception("Could not decorate page with user profile")
        return super().send_html(content, status, extra_headers)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/profile":
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
            return

        if path == "/activity":
            _, session = self.require_session()
            if not session:
                return
            if not core.is_chi_cuc_user(session):
                self.send_html(
                    core.base_page("403", '<div class="container"><div class="notice err">Không có quyền xem lịch sử hoạt động.</div></div>', session),
                    403,
                )
                return
            con = core.db_conn()
            try:
                body = activity_log.activity_page(con, session, parsed.query)
            finally:
                con.close()
            self.send_html(core.base_page("Lịch sử hoạt động", body, session, active_path="/activity"))
            return

        session = self._profile_session()
        if path == "/logout" and session:
            self._write_activity(session, "auth", "logout", "Đăng xuất khỏi hệ thống", success=True)
        self._activity_response_status = None
        super().do_GET()
        spec = activity_log.describe_request(path, "GET")
        if session and spec:
            module, action, detail = spec
            status = self._activity_response_status or 200
            self._write_activity(session, module, action, detail, success=(200 <= status < 400))

    def _handle_login_with_audit(self):
        data = core.parse_body(self)
        username = data.get("username", "").strip()
        password = data.get("password", "")
        con = core.db_conn()
        try:
            user = core.find_user_by_username(con, username)
            ip_address, user_agent = self._audit_meta()
            if not user or not core.verify_password(password, user["password_hash"]):
                if user and core.is_chi_cuc_user(user):
                    activity_log.write_activity(
                        con, user["id"], "login", "Đăng nhập không thành công",
                        module="auth", success=False, ip_address=ip_address, user_agent=user_agent,
                    )
                    con.commit()
                self.send_html(core.login_page("Tên đăng nhập hoặc mật khẩu không đúng."), 401)
                return
            if not user["active"]:
                if core.is_chi_cuc_user(user):
                    activity_log.write_activity(
                        con, user["id"], "login", "Đăng nhập tài khoản không hoạt động",
                        module="auth", success=False, ip_address=ip_address, user_agent=user_agent,
                    )
                    con.commit()
                self.send_html(core.login_page("Tài khoản không hoạt động. Vui lòng liên hệ Chi cục để được xử lý."), 401)
                return
            sid = core.new_session(user)
            if core.is_chi_cuc_user(user):
                activity_log.write_activity(
                    con, user["id"], "login", "Đăng nhập hệ thống",
                    module="auth", success=True, ip_address=ip_address, user_agent=user_agent,
                )
                con.commit()
            self.redirect("/dashboard", [("Set-Cookie", f"salt_session={sid}; Path=/; HttpOnly; SameSite=Lax")])
        finally:
            con.close()

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/login":
            self._handle_login_with_audit()
            return

        if path == "/profile":
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
                self._write_activity(session, "profile", "profile_update", "Cập nhật thông tin cá nhân: CSRF không hợp lệ", success=False)
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
                self._write_activity(session, "profile", "profile_update", f"Cập nhật hồ sơ không thành công: {exc}", success=False)
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
                self._write_activity(session, "profile", "profile_update", "Không thể lưu thông tin cá nhân", success=False)
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

            self._write_activity(session, "profile", "profile_update", "Cập nhật thông tin cá nhân", success=True)
            core.set_flash(session, "ok", "Đã cập nhật thông tin cá nhân.")
            self.redirect("/profile")
            return

        session = self._profile_session()
        self._activity_response_status = None
        super().do_POST()
        spec = activity_log.describe_request(path, "POST")
        if session and spec:
            module, action, detail = spec
            status = self._activity_response_status or 200
            self._write_activity(session, module, action, detail, success=(200 <= status < 400))


core.Handler = Handler


if __name__ == "__main__":
    core.main()
