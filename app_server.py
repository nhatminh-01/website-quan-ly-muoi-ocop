"""Application entry point that composes the existing server with profiles/activity.

There is still a single HTTP server and a single PostgreSQL database. The
existing ``server.py`` remains the business core; this module adds personal
profiles, the account dropdown, activity history and small shell-level routes
without duplicating the salt/OCOP business handlers.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

import server as core
import user_profiles
import activity_log
import ocop_registry
import ocop_services


# Existing record mutations already call server.add_audit. Replacing the global
# function keeps those call sites intact while enriching new rows with user
# snapshots and module metadata.
core.add_audit = activity_log.add_record_audit
CoreHandler = core.Handler


_OCOP_DATA_ENTRY_STYLE = """
<style id="ocop-data-entry-styles">
.ocop-entry-page{max-width:1180px}
.ocop-entry-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px;max-width:920px;margin:0 auto;align-items:stretch}
.ocop-entry-card{display:flex;flex-direction:column;min-height:240px;height:100%;margin:0;padding:26px}
.ocop-entry-card .ocop-entry-icon{display:grid;place-items:center;width:48px;height:48px;border-radius:12px;background:#fff0eb;color:var(--primary);margin-bottom:18px}
.ocop-entry-card .ocop-entry-icon .icon{width:25px;height:25px}
.ocop-entry-card h2{font-size:20px;margin:0 0 10px;color:#24364d}
.ocop-entry-card p{margin:0;color:var(--muted);line-height:1.65}
.ocop-entry-card .actions{margin-top:auto;padding-top:22px}
.ocop-entry-card .btn{width:100%}
@media(max-width:760px){.ocop-entry-grid{grid-template-columns:minmax(0,1fr);max-width:560px}.ocop-entry-card{min-height:0;padding:20px}}
</style>
"""


def ocop_data_entry_body():
    """Choice page only; import/manual business logic stays in their existing routes."""
    return f'''{_OCOP_DATA_ENTRY_STYLE}
    <div class="container ocop-page ocop-entry-page">
      <div class="page-head"><div>
        <div class="ocop-breadcrumb"><a href="/ocop">OCOP</a> / Nhập dữ liệu</div>
        <h1>NHẬP DỮ LIỆU OCOP</h1>
        <div class="subtitle">Chọn một phương thức để bổ sung dữ liệu OCOP vào hệ thống.</div>
      </div></div>
      <div class="ocop-entry-grid" aria-label="Phương thức nhập dữ liệu OCOP">
        <section class="card ocop-entry-card">
          <div class="ocop-entry-icon">{core.icon("download")}</div>
          <h2>Import file Excel</h2>
          <p>Tải file Excel OCOP, xem trước và kiểm tra dữ liệu trước khi xác nhận đồng bộ.</p>
          <div class="actions"><a class="btn primary" href="/ocop/import">Import file Excel</a></div>
        </section>
        <section class="card ocop-entry-card">
          <div class="ocop-entry-icon">{core.icon("plus")}</div>
          <h2>Nhập dữ liệu trực tiếp</h2>
          <p>Nhập trực tiếp thông tin chủ thể, sản phẩm và lịch sử công nhận OCOP.</p>
          <div class="actions"><a class="btn primary" href="/ocop/manual">Nhập dữ liệu trực tiếp</a></div>
        </section>
      </div>
    </div>'''


def _sidebar_anchor(content, href):
    return re.search(
        r'<a class="sidebar-link(?: active)?" href="' + re.escape(href) + r'"[^>]*>.*?</a>',
        content,
        flags=re.S,
    )


def _enhance_ocop_navigation(content, current_path):
    """Render one server-side OCOP data-entry item instead of two method links."""
    import_match = _sidebar_anchor(content, "/ocop/import")
    manual_match = _sidebar_anchor(content, "/ocop/manual")
    source = manual_match or import_match
    if not source:
        return content

    active = current_path == "/ocop/data-entry" or current_path == "/ocop/manual" or current_path.startswith("/ocop/import")
    link = source.group(0)
    link = re.sub(r'href="[^"]+"', 'href="/ocop/data-entry"', link, count=1)
    link = re.sub(r'title="[^"]+"', 'title="Nhập dữ liệu"', link, count=1)
    link = re.sub(r'<span class="sidebar-label">.*?</span>', '<span class="sidebar-label">Nhập dữ liệu</span>', link, count=1, flags=re.S)
    link = re.sub(r'class="sidebar-link(?: active)?"', f'class="sidebar-link{" active" if active else ""}"', link, count=1)
    link = re.sub(r'\saria-current="page"', '', link, count=1)
    if active:
        link = link.replace(' title="Nhập dữ liệu"', ' title="Nhập dữ liệu" aria-current="page"', 1)

    for match in sorted([m for m in (import_match, manual_match) if m], key=lambda m: m.start(), reverse=True):
        content = content[:match.start()] + content[match.end():]

    expiry_match = _sidebar_anchor(content, "/ocop/expiry-alerts")
    if expiry_match:
        content = content[:expiry_match.start()] + link + content[expiry_match.start():]
    return content


def _enhance_ocop_entry_context(content, current_path):
    """Add a consistent way back to the new choice page from both entry methods."""
    if current_path == "/ocop/manual":
        content = content.replace(
            '<div class="ocop-breadcrumb"><a href="/ocop">OCOP</a> / Nhập dữ liệu</div>',
            '<div class="ocop-breadcrumb"><a href="/ocop">OCOP</a> / <a href="/ocop/data-entry">Nhập dữ liệu</a> / Nhập trực tiếp</div>',
            1,
        )
        content = content.replace(
            '<a class="btn" href="/ocop">Hủy</a>',
            '<a class="btn" href="/ocop/data-entry">Quay lại Nhập dữ liệu</a>',
            1,
        )
        if '<div class="container ocop-page manual-page"><h1>NHẬP DỮ LIỆU OCOP</h1>' in content:
            content = content.replace(
                '<div class="container ocop-page manual-page"><h1>NHẬP DỮ LIỆU OCOP</h1>',
                '<div class="container ocop-page manual-page"><div class="ocop-breadcrumb"><a href="/ocop">OCOP</a> / <a href="/ocop/data-entry">Nhập dữ liệu</a> / Nhập trực tiếp</div><h1>NHẬP DỮ LIỆU OCOP</h1>',
                1,
            )
    elif current_path == "/ocop/import":
        content = content.replace(
            '<div class="ocop-breadcrumb"><a href="/ocop">OCOP</a></div>',
            '<div class="ocop-breadcrumb"><a href="/ocop">OCOP</a> / <a href="/ocop/data-entry">Nhập dữ liệu</a> / Import Excel</div>',
            1,
        )
        content = content.replace(
            '<div class="actions"><a class="btn" href="/ocop/recognitions">Lịch sử công nhận</a></div>',
            '<div class="actions"><a class="btn" href="/ocop/data-entry">Quay lại Nhập dữ liệu</a><a class="btn" href="/ocop/recognitions">Lịch sử công nhận</a></div>',
            1,
        )
    elif current_path == "/ocop/import/preview":
        content = content.replace(
            '<div class="ocop-breadcrumb"><a href="/ocop">OCOP</a> / <a href="/ocop/import">Import</a></div>',
            '<div class="ocop-breadcrumb"><a href="/ocop">OCOP</a> / <a href="/ocop/data-entry">Nhập dữ liệu</a> / <a href="/ocop/import">Import Excel</a> / Xem trước</div>',
            1,
        )
    return content


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
        current_path = urlparse(self.path).path
        content = _enhance_ocop_navigation(content, current_path)
        content = _enhance_ocop_entry_context(content, current_path)
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

        if path == "/guide":
            _, session = self.require_session()
            if not session:
                return
            body = """<div class="container profile-page">
              <div class="page-head"><div><h1>Hướng dẫn sử dụng</h1><div class="subtitle">Hướng dẫn nhanh các chức năng chính của hệ thống.</div></div></div>
              <section class="card"><h2 class="section-title">Các chức năng chính</h2>
                <div class="grid">
                  <div><strong>Bảng giám sát</strong><p class="muted">Theo dõi tổng hợp Diêm nghiệp và OCOP theo phạm vi được phép xem.</p></div>
                  <div><strong>Diêm nghiệp</strong><p class="muted">Import báo cáo tuần và tra cứu số liệu sản xuất muối.</p></div>
                  <div><strong>OCOP</strong><p class="muted">Tra cứu, nhập dữ liệu và theo dõi cảnh báo hết hạn.</p></div>
                  <div><strong>Tài khoản</strong><p class="muted">Cập nhật thông tin cá nhân và sử dụng các chức năng theo đúng quyền được cấp.</p></div>
                </div>
              </section>
            </div>"""
            self.send_html(core.base_page("Hướng dẫn sử dụng", body, session))
            return

        if path == "/update-history":
            self.redirect("/activity")
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

        if path == "/ocop/data-entry":
            _, session = self.require_session()
            if not session:
                return
            con = core.db_conn()
            try:
                if not core.ocop_available(con):
                    raise ocop_services.OcopError("Phân hệ OCOP chưa được khởi tạo trên cơ sở dữ liệu này.", 503)
                ocop_registry.require_internal(con, session)
            except ocop_services.OcopError as exc:
                self.send_html(
                    core.base_page(
                        "403" if exc.status == 403 else "Thông báo OCOP",
                        f'<div class="container"><div class="notice err">{core.esc(exc)}</div></div>',
                        session,
                        active_path="/ocop/manual",
                    ),
                    exc.status,
                )
                return
            finally:
                con.close()
            # Use an existing OCOP entry path only to keep the core sidebar group
            # open; send_html replaces the two method links with /ocop/data-entry.
            self.send_html(core.base_page("Nhập dữ liệu OCOP", ocop_data_entry_body(), session, active_path="/ocop/manual"))
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
            if not user["active"] or not core.is_chi_cuc_user(user):
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
