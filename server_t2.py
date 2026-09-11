#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PostgreSQL web entry point with OCOP T2 historical import routes.

The mature salt/OCOP handlers remain in ``server.py``.  This thin entry point
adds the T2 import/recognition routes without duplicating the existing server.
"""
from __future__ import annotations

import argparse
import logging
import sys
from http.server import ThreadingHTTPServer
from urllib.parse import urlparse

import admin_units
import ocop_import
import ocop_import_pages
import ocop_pages
from permissions import is_chi_cuc_user
import server as core


_original_base_page = core.base_page
_original_ocop_render = ocop_pages.render


def _sidebar_link(href, symbol, label, active=False):
    active_attr = " active" if active else ""
    current = ' aria-current="page"' if active else ""
    return (
        f'<a class="sidebar-link{active_attr}" href="{href}" title="{label}"{current}>'
        f'{core.icon(symbol)}<span class="sidebar-label">{label}</span></a>'
    )


def enhanced_base_page(title, body, session=None, active_path=None):
    requested = active_path or ""
    # Keep the OCOP details group expanded for the new T2 routes.
    group_active = "/ocop" if requested in ("/ocop/import", "/ocop/recognitions") else active_path
    html = _original_base_page(title, body, session, active_path=group_active)
    if not session:
        return html
    start = html.find('<details class="sidebar-group" data-group="ocop"')
    if start < 0:
        return html
    end = html.find("</div></details>", start)
    if end < 0:
        return html
    extra = _sidebar_link(
        "/ocop/recognitions", "file", "Lịch sử công nhận",
        requested == "/ocop/recognitions",
    )
    if is_chi_cuc_user(session):
        extra += _sidebar_link(
            "/ocop/import", "download", "Import Excel OCOP",
            requested == "/ocop/import",
        )
    return html[:end] + extra + html[end:]


def enhanced_ocop_render(path, query, session, con, helpers):
    result = _original_ocop_render(path, query, session, con, helpers)
    clean = str(path or "").rstrip("/")
    if result and clean.startswith("/ocop/products/") and not clean.endswith("/edit"):
        parts = clean.strip("/").split("/")
        if len(parts) == 3 and parts[2].isdigit():
            section = ocop_import_pages.product_history_section(con, session, int(parts[2]))
            if section:
                title, body = result
                pos = body.rfind("</div>")
                if pos >= 0:
                    body = body[:pos] + section + body[pos:]
                else:
                    body += section
                result = (title, body)
    return result


# Patch only presentation hooks. Existing business handlers continue to resolve
# these module globals at request time.
core.base_page = enhanced_base_page
ocop_pages.render = enhanced_ocop_render


class T2Handler(core.Handler):
    def _helpers(self):
        return {
            "csrf_input": core.csrf_input,
            "take_flash": core.take_flash,
            "esc": core.esc,
        }

    def _send_t2_page(self, title, body, status, session, active_path):
        self.send_html(core.base_page(title, body, session, active_path=active_path), status)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path not in ("/ocop/import", "/ocop/import/preview", "/ocop/recognitions"):
            return super().do_GET()
        _, session = self.require_session()
        if not session:
            return
        con = core.db_conn()
        try:
            if path == "/ocop/import":
                title, body, status = ocop_import_pages.import_page(session, con, self._helpers())
                return self._send_t2_page(title, body, status, session, "/ocop/import")
            if path == "/ocop/import/preview":
                if not is_chi_cuc_user(session):
                    return self._send_t2_page(
                        "403", '<div class="container"><div class="notice err">Không có quyền.</div></div>',
                        403, session, "/ocop/import",
                    )
                upload = session.get("ocop_import_upload")
                if not upload:
                    core.set_flash(session, "err", "Dữ liệu xem trước đã hết hạn. Hãy chọn lại file.")
                    return self.redirect("/ocop/import")
                preview = ocop_import.parse_ocop_workbook(
                    upload["content"], upload["filename"], admin_units.unit_lookup(con), upload["sheet_name"]
                )
                title, body, status = ocop_import_pages.preview_page(session, preview, self._helpers())
                return self._send_t2_page(title, body, status, session, "/ocop/import")
            title, body, status = ocop_import_pages.recognitions_page(
                session, con, parsed.query, self._helpers()
            )
            return self._send_t2_page(title, body, status, session, "/ocop/recognitions")
        except (ocop_import.OcopImportError, Exception) as exc:
            # Preserve a friendly response while still logging unexpected failures.
            if not isinstance(exc, ocop_import.OcopImportError):
                logging.exception("OCOP T2 GET failed")
            body = f'<div class="container"><div class="notice err">{core.esc(exc)}</div><a class="btn" href="/ocop">Quay lại OCOP</a></div>'
            return self._send_t2_page("Thông báo OCOP", body, 400 if isinstance(exc, ocop_import.OcopImportError) else 500, session, "/ocop/import")
        finally:
            con.close()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path not in ("/ocop/import", "/ocop/import/confirm"):
            return super().do_POST()
        _, session = self.require_session()
        if not session:
            return
        if not is_chi_cuc_user(session):
            return self._send_t2_page(
                "403", '<div class="container"><div class="notice err">Chỉ tài khoản Chi cục được import OCOP.</div></div>',
                403, session, "/ocop/import",
            )
        if path == "/ocop/import":
            try:
                data, uploaded_files = core.parse_multipart_form(self)
                if not core.check_csrf(session, data):
                    raise ocop_import.OcopImportError("Phiên làm việc không hợp lệ. Vui lòng tải lại trang.")
                uploaded = uploaded_files.get("excel_file")
                if not uploaded:
                    raise ocop_import.OcopImportError("Vui lòng chọn file Excel OCOP.")
                filename = uploaded.get("filename") or ""
                sheet_name = str(data.get("sheet_name", "Loc")).strip() or "Loc"
                con = core.db_conn()
                try:
                    # Parse once before storing the preview source, so malformed files
                    # never enter the session state.
                    ocop_import.parse_ocop_workbook(
                        uploaded["content"], filename, admin_units.unit_lookup(con), sheet_name
                    )
                finally:
                    con.close()
                session["ocop_import_upload"] = {
                    "content": uploaded["content"],
                    "filename": filename,
                    "sheet_name": sheet_name,
                }
                return self.redirect("/ocop/import/preview")
            except ocop_import.OcopImportError as exc:
                core.set_flash(session, "err", str(exc))
                return self.redirect("/ocop/import")
            except Exception:
                logging.exception("OCOP upload failed")
                core.set_flash(session, "err", "Không thể đọc file OCOP lúc này.")
                return self.redirect("/ocop/import")

        data = core.parse_body(self)
        if not core.check_csrf(session, data):
            return self._send_t2_page(
                "Lỗi", '<div class="container"><div class="notice err">Phiên làm việc không hợp lệ. Vui lòng tải lại trang.</div></div>',
                403, session, "/ocop/import",
            )
        upload = session.get("ocop_import_upload")
        if not upload:
            core.set_flash(session, "err", "Dữ liệu xem trước đã hết hạn. Hãy chọn lại file.")
            return self.redirect("/ocop/import")
        con = core.db_conn()
        try:
            preview = ocop_import.parse_ocop_workbook(
                upload["content"], upload["filename"], admin_units.unit_lookup(con), upload["sheet_name"]
            )
            con.execute("BEGIN")
            result = ocop_import.commit_ocop_preview(con, session, preview, data.get("mode", "publish"))
            con.commit()
        except ocop_import.OcopImportError as exc:
            con.rollback()
            core.set_flash(session, "err", str(exc))
            return self.redirect("/ocop/import/preview")
        except core.INTEGRITY_ERRORS:
            con.rollback()
            core.set_flash(session, "err", "Dữ liệu bị trùng hoặc thay đổi trong lúc import. Hãy xem trước lại.")
            return self.redirect("/ocop/import/preview")
        except Exception:
            con.rollback()
            logging.exception("OCOP T2 publish failed")
            core.set_flash(session, "err", "Không thể đồng bộ OCOP; transaction đã được hoàn tác.")
            return self.redirect("/ocop/import/preview")
        finally:
            con.close()
        session.pop("ocop_import_upload", None)
        if result.get("already_published"):
            core.set_flash(session, "ok", "File này đã được đồng bộ trước đó; không tạo dữ liệu trùng.")
        elif data.get("mode") == "stage_only":
            core.set_flash(session, "ok", f"Đã lưu staging đợt #{result['batch_id']} để đối chiếu; chưa ghi dữ liệu OCOP chính thức.")
        else:
            core.set_flash(session, "ok", f"Đã đồng bộ {result['published_products']} sản phẩm OCOP từ đợt #{result['batch_id']}.")
        return self.redirect("/ocop/recognitions" if data.get("mode") != "stage_only" else "/ocop/import")


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Hệ thống quản lý nghiệp vụ Chi cục Phát triển nông thôn")
    parser.add_argument("--host", default=core.HOST)
    parser.add_argument("--port", type=int, default=core.PORT)
    args = parser.parse_args()
    core.init_db()
    con = core.db_conn()
    try:
        ready = con.execute(
            """SELECT to_regclass('app.ocop_recognitions') AS recognitions,
                      to_regclass('staging.ocop_import_batches') AS batches,
                      to_regclass('staging.ocop_import_rows') AS import_rows"""
        ).fetchone()
        if not all(ready.values()):
            raise RuntimeError("Thiếu migration 013_ocop_legacy_import.sql. Hãy áp dụng migration 013 trước khi chạy web.")
    finally:
        con.close()
    httpd = ThreadingHTTPServer((args.host, args.port), T2Handler)
    settings = core.load_settings()
    print("=" * 72)
    print("HỆ THỐNG QUẢN LÝ NGHIỆP VỤ - PostgreSQL + OCOP T2")
    print(f"Database PostgreSQL: {settings.dbname} @ {settings.host}:{settings.port}")
    print(f"Đang chạy tại: http://127.0.0.1:{args.port}")
    print(f"Trong mạng LAN: http://<IP-máy-chủ>:{args.port}")
    print("Nhấn Ctrl+C để dừng.")
    print("=" * 72)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nĐã dừng máy chủ.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
