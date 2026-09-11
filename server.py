#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Website nội bộ quản lý số liệu sản xuất muối
- Không cần Flask/Django; dữ liệu được lưu tập trung trên PostgreSQL.
- openpyxl là tùy chọn để xuất Excel .xlsx.

Chạy: python server.py
Mặc định: http://0.0.0.0:8080
"""

from __future__ import annotations

import csv
import argparse
import hashlib
import html
import io
import json
import os
import re
import secrets
import sys
import threading
import time
import logging
from backend_db import compat_connect, load_settings, INTEGRITY_ERRORS
from permissions import (ROLE_ADMIN, ROLE_STAFF, ROLE_UNIT, ROLE_LABELS,
                         is_admin, is_chi_cuc_user, can_manage_users, can_review_records)
from salt_normalization import sync_methods
from weekly_import import WeeklyImportError, parse_weekly_workbook, commit_weekly_preview, effective_weekly_dashboard
import repositories
from datetime import datetime, date
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse
from email.parser import BytesParser
from email.policy import default

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSET_FILES = {
    "/assets/quoc-huy.png": ("quoc-huy.png", "image/png"),
    "/assets/app.css": ("app.css", "text/css; charset=utf-8"),
    "/assets/app.js": ("app.js", "text/javascript; charset=utf-8"),
}
HOST = os.environ.get("SALT_WEB_HOST", "0.0.0.0")
PORT = int(os.environ.get("SALT_WEB_PORT", "8080"))

STATUS_DRAFT = "draft"
STATUS_SUBMITTED = "submitted"
STATUS_APPROVED = "approved"
STATUS_RETURNED = "returned"

STATUS_LABELS = {
    STATUS_DRAFT: "Bản nháp",
    STATUS_SUBMITTED: "Đã gửi Chi cục",
    STATUS_APPROVED: "Đã duyệt",
    STATUS_RETURNED: "Yêu cầu chỉnh sửa",
}

SESSIONS: dict[str, dict] = {}
SESSION_LOCK = threading.Lock()

UNITS = [
    "Xã An Thới Đông",
    "Xã Thạnh An",
    "Xã Cần Giờ",
    "Xã Long Điền",
    "Xã Long Sơn",
    "Phường Phước Thắng",
    "Phường Long Hương",
    "Phường Bà Rịa",
]

# Mã đơn vị hành chính chính thức theo Quyết định 19/2025/QĐ-TTg.
HCMC_ADMIN_CODE = "79"
HCMC_ADMIN_NAME = "Thành phố Hồ Chí Minh"
OFFICIAL_ADMIN_UNITS = {
    "Xã An Thới Đông": ("27673", "xa"),
    "Xã Thạnh An": ("27676", "xa"),
    "Xã Cần Giờ": ("27664", "xa"),
    "Xã Long Điền": ("26659", "xa"),
    "Xã Long Sơn": ("26545", "xa"),
    "Phường Phước Thắng": ("26542", "phuong"),
    "Phường Long Hương": ("26566", "phuong"),
    "Phường Bà Rịa": ("26560", "phuong"),
}
OFFICIAL_ADMIN_LOOKUP = {name.casefold(): value for name, value in OFFICIAL_ADMIN_UNITS.items()}
OFFICIAL_ADMIN_LOOKUP["xã an thời đông".casefold()] = OFFICIAL_ADMIN_UNITS["Xã An Thới Đông"]
OFFICIAL_ADMIN_NAMES_BY_CODE = {code: name for name, (code, _level) in OFFICIAL_ADMIN_UNITS.items()}

NUMERIC_FIELDS = [
    "area_land", "area_tarp",
    "harvest_land", "harvest_tarp",
    "sold_land", "sold_tarp",
    "remaining_land", "remaining_tarp",
    "processed_fine", "processed_iodized",
    "households", "workers",
    "damage_land", "damage_tarp",
]

FIELD_LABELS = {
    "area_land": "Diện tích muối đất (ha)",
    "area_tarp": "Diện tích muối trải bạt (ha)",
    "harvest_land": "Thu hoạch muối đất (tấn)",
    "harvest_tarp": "Thu hoạch muối trải bạt (tấn)",
    "sold_land": "Tiêu thụ muối đất (tấn)",
    "sold_tarp": "Tiêu thụ muối trải bạt (tấn)",
    "remaining_land": "Còn lại muối đất (tấn)",
    "remaining_tarp": "Còn lại muối trải bạt (tấn)",
    "processed_fine": "Muối tinh chế biến (tấn)",
    "processed_iodized": "Muối I-ốt chế biến (tấn)",
    "households": "Số hộ làm muối (hộ)",
    "workers": "Số lao động làm muối (người)",
    "price_land": "Giá bán muối đất (đồng/kg)",
    "price_tarp": "Giá bán muối trải bạt (đồng/kg)",
    "damage_land": "Thiệt hại muối đất (tấn)",
    "damage_tarp": "Thiệt hại muối trải bạt (tấn)",
}

def esc(value):
    return html.escape("" if value is None else str(value), quote=True)


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def hash_password(password: str, salt: str | None = None) -> str:
    if salt is None:
        salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 160_000)
    return f"{salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, expected = stored.split("$", 1)
        actual = hash_password(password, salt).split("$", 1)[1]
        return secrets.compare_digest(actual, expected)
    except Exception:
        return False


def db_conn():
    return compat_connect()


def get_user(con, user_id):
    return repositories.get_user(con, user_id)


def find_user_by_username(con, username):
    return repositories.find_user_by_username(con, username)


def find_active_user(con, username):
    user = find_user_by_username(con, username)
    return user if user and user["active"] else None


def create_user(con, username, password_hash, role, unit_name, created_at):
    return repositories.create_user(con, username, password_hash, role, unit_name, created_at)


def set_user_password(con, user_id, password_hash):
    repositories.set_local_password(con, user_id, password_hash)


def update_user_account(con, user_id, username, role, unit_name, active, password_hash=None):
    repositories.update_user(con, user_id, username, role, unit_name, active, password_hash)


def delete_user_account(con, user_id):
    repositories.delete_user(con, user_id)


def ocop_available(con=None):
    """Return whether the required PostgreSQL application schema is ready."""
    own = con is None
    if own:
        con = db_conn()
    try:
        return repositories.postgres_application_ready(con)
    finally:
        if own:
            con.close()


def invalidate_user_sessions(user_id, keep_sid=None):
    with SESSION_LOCK:
        for sid in list(SESSIONS):
            if SESSIONS[sid]["user_id"] == user_id and sid != keep_sid:
                SESSIONS.pop(sid, None)


def ocop_user_links(con, user_id):
    if not ocop_available(con):
        return 0
    total = 0
    for table, column in (("ocop_entities", "created_by"), ("ocop_products", "created_by"),
                          ("ocop_applications", "created_by"), ("ocop_applications", "reviewer_id"),
                          ("ocop_reviews", "reviewer_id"), ("user_admin_units", "user_id")):
        total += con.execute(f"SELECT COUNT(*) FROM {table} WHERE {column}=?", (user_id,)).fetchone()[0]
    return total


def init_db():
    con = db_conn()
    try:
        if not repositories.postgres_application_ready(con):
            raise RuntimeError("PostgreSQL chưa có schema app. Chạy database/sql/004_app_schema.sql trước.")
        seed_official_admin_units(con)
        con.commit()
    finally:
        con.close()


def add_audit(con, record_id, user_id, action, detail=""):
    con.execute(
        "INSERT INTO audit_logs(record_id,user_id,action,detail,created_at) VALUES(?,?,?,?,?)",
        (record_id, user_id, action, detail, now_text()),
    )


def fnum(v):
    if v is None or v == "":
        return 0.0
    try:
        return float(str(v).replace(",", "."))
    except ValueError:
        return 0.0


def fint(v):
    try:
        return int(float(str(v).replace(",", ".")))
    except (ValueError, TypeError):
        return 0


def _parse_vietnamese_number(value):
    """Đọc số theo cách người dùng Việt Nam thường nhập: 1.500; 1,500; 1500; 1.500,50."""
    if value is None:
        return None
    token = str(value).strip().replace(" ", "")
    if not token:
        return None

    # Có cả dấu chấm và dấu phẩy: ưu tiên kiểu Việt Nam 1.500,50.
    if "." in token and "," in token:
        if token.rfind(",") > token.rfind("."):
            token = token.replace(".", "").replace(",", ".")
        else:
            token = token.replace(",", "")
    elif "." in token:
        parts = token.split(".")
        # 1.500 hoặc 12.500.000 -> dấu chấm là phân cách hàng nghìn.
        if len(parts) > 1 and all(len(x) == 3 for x in parts[1:]):
            token = "".join(parts)
    elif "," in token:
        parts = token.split(",")
        # Giá bán thường nhập nguyên đồng/kg; 1,500 được hiểu là 1500.
        if len(parts) > 1 and all(len(x) == 3 for x in parts[1:]):
            token = "".join(parts)
        else:
            token = token.replace(",", ".")

    try:
        return float(token)
    except ValueError:
        return None


def price_average(value):
    """Chuyển ô giá dạng '1.000 - 1.500' thành giá bình quân 1250."""
    if value is None:
        return 0.0
    text = str(value).strip()
    if not text:
        return 0.0

    tokens = re.findall(r"\d[\d.,]*", text)
    numbers = []
    for token in tokens:
        n = _parse_vietnamese_number(token)
        if n is not None:
            numbers.append(n)

    if not numbers:
        return 0.0
    if len(numbers) == 1:
        return round(numbers[0], 2)
    return round((numbers[0] + numbers[1]) / 2.0, 2)


def _temporary_unit_code(unit_name):
    """Mã nội bộ tạm thời cho đơn vị ngoài danh mục chính thức đã cấu hình."""
    digest = hashlib.sha1(unit_name.casefold().encode("utf-8")).hexdigest()[:7].upper()
    return "TMP" + digest


def canonical_admin_unit(unit_name):
    """Return the configured official name/code, including known source aliases."""
    official = OFFICIAL_ADMIN_LOOKUP.get(str(unit_name).strip().casefold())
    if not official:
        return None
    code, _level = official
    return OFFICIAL_ADMIN_NAMES_BY_CODE[code], code


def seed_official_admin_units(con):
    """Tạo/cập nhật danh mục đơn vị hành chính chính thức của hệ thống."""
    con.execute(
        """
        INSERT INTO DM_DonViHanhChinh
        (Ma_DonViHanhChinh, Ma_DonViCapTren, TenDonVi, CapHanhChinh, TinhTrang)
        VALUES(?, NULL, ?, 'tinh', TRUE)
        ON CONFLICT(Ma_DonViHanhChinh) DO UPDATE SET
            TenDonVi=excluded.TenDonVi,
            CapHanhChinh=excluded.CapHanhChinh,
            TinhTrang=TRUE
        """,
        (HCMC_ADMIN_CODE, HCMC_ADMIN_NAME),
    )

    for unit_name, (code, level) in OFFICIAL_ADMIN_UNITS.items():
        con.execute(
            """
            INSERT INTO DM_DonViHanhChinh
            (Ma_DonViHanhChinh, Ma_DonViCapTren, TenDonVi, CapHanhChinh, TinhTrang)
            VALUES(?, ?, ?, ?, TRUE)
            ON CONFLICT(Ma_DonViHanhChinh) DO UPDATE SET
                Ma_DonViCapTren=excluded.Ma_DonViCapTren,
                TenDonVi=excluded.TenDonVi,
                CapHanhChinh=excluded.CapHanhChinh,
                TinhTrang=TRUE
            """,
            (code, HCMC_ADMIN_CODE, unit_name, level),
        )


def migrate_temporary_unit_codes(con):
    """Chuyển các bản ghi chuẩn hóa đang dùng TMP... sang mã hành chính chính thức."""
    migrated = 0
    for unit_name, (official_code, _level) in OFFICIAL_ADMIN_UNITS.items():
        old_rows = con.execute(
            """
            SELECT Ma_DonViHanhChinh
            FROM DM_DonViHanhChinh
            WHERE lower(TenDonVi)=lower(?)
              AND Ma_DonViHanhChinh LIKE 'TMP%'
            """,
            (unit_name,),
        ).fetchall()

        for old in old_rows:
            old_code = old["Ma_DonViHanhChinh"]
            standard_rows = con.execute(
                "SELECT * FROM DN_SanLuongMuoi WHERE Ma_DonViHanhChinh=?",
                (old_code,),
            ).fetchall()

            for r in standard_rows:
                con.execute(
                    """
                    INSERT INTO DN_SanLuongMuoi
                    (Ma_DonViHanhChinh, Ma_ThoiGian, PhuongPhapSX, DienTich, SanLuong, GiaBanBinhQuan)
                    VALUES(?,?,?,?,?,?)
                    ON CONFLICT(Ma_DonViHanhChinh, Ma_ThoiGian, PhuongPhapSX) DO UPDATE SET
                        DienTich=excluded.DienTich,
                        SanLuong=excluded.SanLuong,
                        GiaBanBinhQuan=excluded.GiaBanBinhQuan
                    """,
                    (official_code, r["Ma_ThoiGian"], r["PhuongPhapSX"],
                     r["DienTich"], r["SanLuong"], r["GiaBanBinhQuan"]),
                )
                migrated += 1

            con.execute(
                "DELETE FROM DN_SanLuongMuoi WHERE Ma_DonViHanhChinh=?",
                (old_code,),
            )
            con.execute(
                "DELETE FROM DM_DonViHanhChinh WHERE Ma_DonViHanhChinh=?",
                (old_code,),
            )

    return migrated


def ensure_standard_unit(con, unit_name):
    """Ưu tiên mã hành chính chính thức; chỉ dùng TMP cho đơn vị chưa có trong danh mục."""
    official = OFFICIAL_ADMIN_LOOKUP.get(str(unit_name).strip().casefold())
    if official:
        code, _level = official
        return code

    row = con.execute(
        "SELECT Ma_DonViHanhChinh FROM DM_DonViHanhChinh WHERE lower(TenDonVi)=lower(?) ORDER BY CASE WHEN Ma_DonViHanhChinh LIKE 'TMP%' THEN 1 ELSE 0 END LIMIT 1",
        (unit_name,),
    ).fetchone()
    if row:
        return row["Ma_DonViHanhChinh"]

    code = _temporary_unit_code(unit_name)
    lower_name = unit_name.casefold()
    if lower_name.startswith("phường "):
        level = "phuong"
    elif lower_name.startswith("xã "):
        level = "xa"
    elif lower_name.startswith("thị trấn "):
        level = "thitran"
    else:
        level = "xa"

    con.execute(
        """
        INSERT INTO DM_DonViHanhChinh
        (Ma_DonViHanhChinh, Ma_DonViCapTren, TenDonVi, CapHanhChinh, TinhTrang)
        VALUES(?, NULL, ?, ?, TRUE)
        ON CONFLICT(Ma_DonViHanhChinh) DO NOTHING
        """,
        (code, unit_name, level),
    )
    return code

def ensure_standard_time(con, report_date):
    """Tạo mã kỳ tháng YYYY-MM cho dữ liệu tổng hợp chuẩn."""
    d = date.fromisoformat(str(report_date))
    code = d.strftime("%Y-%m")
    con.execute(
        """
        INSERT INTO DM_KhoangThoiGian(Ma_ThoiGian, Nam, Thang, VuMua)
        VALUES(?, ?, ?, NULL)
        ON CONFLICT(Ma_ThoiGian) DO NOTHING
        """,
        (code, d.year, d.month),
    )
    return code


def sync_standard_salt_record(con, record):
    """Đồng bộ báo cáo lũy tiến mới nhất thành một dòng muối truyền thống/tháng."""
    if not record:
        return

    unit_code = ensure_standard_unit(con, record["unit_name"])
    time_code = ensure_standard_time(con, record["report_date"])
    month_start = date.fromisoformat(str(record["report_date"])).replace(day=1)
    next_month = date(month_start.year + (month_start.month == 12), (month_start.month % 12) + 1, 1)
    latest = con.execute(
        """SELECT * FROM records
           WHERE unit_name=? AND status='approved'
             AND report_date>=? AND report_date<? AND reporting_mode='cumulative'""" +
        " ORDER BY report_date DESC, id DESC LIMIT 1",
        (record["unit_name"], month_start.isoformat(), next_month.isoformat()),
    ).fetchone()

    sync_methods(con.execute, unit_code, time_code, latest, postgres=True)


def sync_all_approved_records():
    """Có thể gọi thủ công khi cần đồng bộ lại toàn bộ dữ liệu đã duyệt."""
    con = db_conn()
    try:
        rows = con.execute(
            "SELECT * FROM records WHERE status=? ORDER BY report_date, unit_name",
            (STATUS_APPROVED,),
        ).fetchall()
        for row in rows:
            sync_standard_salt_record(con, row)
        con.commit()
        return len(rows)
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def fmt_num(v, decimals=1):
    try:
        n = float(v or 0)
    except Exception:
        n = 0
    if abs(n - round(n)) < 1e-10:
        return f"{int(round(n)):,}".replace(",", ".")
    s = f"{n:,.{decimals}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def record_totals(r):
    area_total = (r["area_land"] or 0) + (r["area_tarp"] or 0)
    harvest_total = (r["harvest_land"] or 0) + (r["harvest_tarp"] or 0)
    sold_total = (r["sold_land"] or 0) + (r["sold_tarp"] or 0)
    remaining_total = (r["remaining_land"] or 0) + (r["remaining_tarp"] or 0)
    processed_total = (r["processed_fine"] or 0) + (r["processed_iodized"] or 0)
    damage_total = (r["damage_land"] or 0) + (r["damage_tarp"] or 0)
    avg_yield = harvest_total / area_total if area_total else 0
    return {
        "area_total": area_total,
        "harvest_total": harvest_total,
        "sold_total": sold_total,
        "remaining_total": remaining_total,
        "processed_total": processed_total,
        "damage_total": damage_total,
        "avg_yield": avg_yield,
    }


def parse_body(handler):
    length = int(handler.headers.get("Content-Length", "0") or 0)
    raw = handler.rfile.read(length).decode("utf-8", errors="replace")
    parsed = parse_qs(raw, keep_blank_values=True)
    return {k: v[-1] if v else "" for k, v in parsed.items()}

def parse_multipart_form(handler):
    content_type = handler.headers.get("Content-Type", "")
    length = int(handler.headers.get("Content-Length", "0") or 0)

    raw_body = handler.rfile.read(length)

    raw_message = (
        f"Content-Type: {content_type}\r\n"
        f"MIME-Version: 1.0\r\n\r\n"
    ).encode("utf-8") + raw_body

    message = BytesParser(policy=default).parsebytes(raw_message)

    fields = {}
    files = {}

    if not message.is_multipart():
        return fields, files

    for part in message.iter_parts():
        name = part.get_param(
            "name",
            header="Content-Disposition"
        )

        if not name:
            continue

        payload = part.get_payload(decode=True) or b""
        filename = part.get_filename()

        if filename:
            files[name] = {
                "filename": filename,
                "content": payload,
                "content_type": part.get_content_type()
            }

        else:
            charset = part.get_content_charset() or "utf-8"

            fields[name] = payload.decode(
                charset,
                errors="replace"
            )

    return fields, files


def excel_text(value):
    if value is None:
        return ""

    if isinstance(value, float) and value.is_integer():
        return str(int(value))

    return str(value).strip()

def new_session(user_row):
    sid = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    with SESSION_LOCK:
        SESSIONS[sid] = {
            "user_id": user_row["id"],
            "username": user_row["username"],
            "role": user_row["role"],
            "unit_name": user_row["unit_name"],
            "csrf": csrf,
            "created": time.time(),
            "auth_version": user_row["password_hash"],
            "flash": None,
        }
    return sid


def get_session(handler):
    raw = handler.headers.get("Cookie", "")
    jar = cookies.SimpleCookie()
    try:
        jar.load(raw)
    except Exception:
        return None, None
    morsel = jar.get("salt_session")
    if not morsel:
        return None, None
    sid = morsel.value
    with SESSION_LOCK:
        s = SESSIONS.get(sid)
    if s:
        con = db_conn()
        try:
            current = get_user(con, s["user_id"])
        finally:
            con.close()
        if (not current or not current["active"] or current["role"] not in tuple(ROLE_LABELS)
                or s.get("auth_version") != current["password_hash"]):
            with SESSION_LOCK:
                SESSIONS.pop(sid, None)
            return None, None
        # Authorization reflects account changes on the next request.
        s.update(username=current["username"], role=current["role"], unit_name=current["unit_name"])
    return sid, s


def set_flash(session, kind, text):
    session["flash"] = (kind, text)


def take_flash(session):
    if not session:
        return ""
    item = session.get("flash")
    session["flash"] = None
    if not item:
        return ""
    kind, text = item
    return f'<div class="notice {esc(kind)}">{esc(text)}</div>'


def csrf_input(session):
    return f'<input type="hidden" name="csrf" value="{esc(session["csrf"])}">'


def check_csrf(session, data):
    return bool(session and secrets.compare_digest(str(data.get("csrf", "")), str(session.get("csrf", ""))))


def account_display_name(session):
    """Tên trên giao diện; không thay đổi tên đơn vị dùng để lọc báo cáo."""
    username = str(session.get("username") or "").strip()
    account_key = username.casefold().replace("_", "").replace("-", "").replace(" ", "")
    account_names = {
        "chicuc": "CHI CỤC PHÁT TRIỂN NÔNG THÔN THÀNH PHỐ HỒ CHÍ MINH",
        "cangio": "XÃ CẦN GIỜ",
    }
    unit_name = str(session.get("unit_name") or "").strip()
    return account_names.get(account_key, (unit_name or username).upper())


def icon(name):
    paths = {
        "dashboard": '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
        "table": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M3 15h18M9 4v16"/>',
        "plus": '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M12 8v8M8 12h8"/>',
        "users": '<circle cx="9" cy="8" r="3"/><path d="M3 21v-2a6 6 0 0 1 12 0v2M16 5a3 3 0 0 1 0 6M21 21v-2a6 6 0 0 0-4-5"/>',
        "key": '<circle cx="8" cy="8" r="5"/><path d="m12 12 9 9m-3-3 3-3m-6 0 3-3"/>',
        "search": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
        "menu": '<path d="M4 6h16M4 12h16M4 18h16"/>',
        "logout": '<path d="M9 4H4v16h5M9 12h12m-4-4 4 4-4 4"/>',
        "file": '<path d="M14 2H5v20h14V7zM14 2v6h5M8 12h8M8 16h8"/>',
        "send": '<path d="m22 2-7 20-4-9-9-4 20-7ZM22 2 11 13"/>',
        "check": '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="m8 12 3 3 6-6"/>',
        "return": '<path d="m8 4-5 5 5 5M3 9h11a7 7 0 0 1 0 14"/>',
        "chart": '<path d="M3 3v18h18M7 15l4-5 4 2 5-7M16 5h4v4"/>',
        "area": '<path d="m12 3 10 5-10 5L2 8 12 3ZM2 12l10 5 10-5M2 16l10 5 10-5"/>',
        "harvest": '<path d="M4 20V9h16v11zM4 9l8-6 8 6M8 13h8M8 17h8"/>',
        "sold": '<path d="M3 5h3l3 12h10l2-9H7"/><circle cx="10" cy="21" r="1"/><circle cx="18" cy="21" r="1"/>',
        "stock": '<path d="m12 3 9 5v10l-9 5-9-5V8l9-5ZM3 8l9 5 9-5M12 13v10M8 5l9 5"/>',
        "home": '<path d="m3 10 9-7 9 7v11H3zM9 21v-8h6v8"/>',
        "download": '<path d="M12 3v12m-5-5 5 5 5-5M4 15v6h16v-6"/>',
        "location": '<path d="M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="2.5"/>',
    }
    return f'<svg class="icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">{paths.get(name, paths["file"])}</svg>'


def sidebar_group(group, items, current):
    links = []
    for href, symbol, label in items:
        active = href == current
        links.append(f'<a class="sidebar-link{" active" if active else ""}" href="{href}" title="{label}"'
                     + (' aria-current="page"' if active else '')
                     + f'>{icon(symbol)}<span class="sidebar-label">{label}</span></a>')
    content = ''.join(links)
    if group not in ("DIÊM NGHIỆP", "OCOP"):
        return f'<div class="sidebar-section">{group}</div>{content}'
    key = "ocop" if group == "OCOP" else "salt"
    active = any(href == current for href, _, _ in items)
    return (f'<details class="sidebar-group" data-group="{key}" data-active="{str(active).lower()}"'
            + (' open' if active else '') + f'><summary title="{group}"><span class="group-label">{group}</span>'
            + '<svg class="group-chevron icon" viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>'
            + f'</summary><div class="sidebar-group-links">{content}</div></details>')


def salt_data_tabs(session, current):
    """Keep weekly lookup visible inside the salt-data workflow."""
    items = [
        ("/records", "Dữ liệu báo cáo"),
        ("/salt/weekly", "Tra cứu theo tuần"),
    ]
    if is_chi_cuc_user(session):
        items.append(("/import-excel", "Import Excel tuần"))
        items.append(("/standard-data", "Dữ liệu chuẩn QĐ 5277"))
    links = ''.join(
        f'<a class="salt-tab{" active" if href == current else ""}" href="{href}"'
        + (' aria-current="page"' if href == current else '')
        + f'>{label}</a>'
        for href, label in items
    )
    return f'<nav class="salt-tabs" aria-label="Dữ liệu diêm nghiệp">{links}</nav>'


def base_page(title, body, session=None, active_path=None):
    top = ""
    if session:
        current = {
            "Tổng quan": "/dashboard",
            "Tài khoản": "/users",
            "Sửa tài khoản": "/users",
            "Đổi mật khẩu": "/change-password",
            "Nhập số liệu": "/records/new",
            "Dữ liệu báo cáo": "/records",
            "Chi tiết báo cáo": "/records",
            "Yêu cầu chỉnh sửa": "/records",
            "Import Excel": "/records/new",
            "Import báo cáo tuần": "/import-excel",
            "Xem trước import tuần": "/import-excel",
            "Tra cứu báo cáo tuần": "/salt/weekly",
            "Dữ liệu chuẩn hóa": "/records",
        }.get(title, "/records")
        current = active_path or ("/standard-data" if title == "Dữ liệu chuẩn hóa" else current)
        salt_items = [("/records", "table", "Dữ liệu sản xuất muối"),
                      ("/records/new", "plus", "Nhập số liệu"),
                      ("/salt/weekly", "table", "Tra cứu báo cáo tuần")]
        system_items = []
        if is_chi_cuc_user(session):
            salt_items.append(("/import-excel", "download", "Import báo cáo tuần"))
            salt_items.append(("/standard-data", "file", "Dữ liệu chuẩn hóa"))
        if can_manage_users(session):
            system_items.append(("/users", "users", "Tài khoản"))
        system_items.extend([("/change-password", "key", "Đổi mật khẩu"),
                             ("/logout", "logout", "Đăng xuất")])
        nav_groups = [("TỔNG QUAN", [("/dashboard", "dashboard", "Bảng giám sát")]),
                      ("DIÊM NGHIỆP", salt_items)]
        if ocop_available():
            nav_groups.append(("OCOP", [("/ocop", "dashboard", "Tổng quan OCOP"),
                                        ("/ocop/products", "table", "Sản phẩm OCOP"),
                                        ("/ocop/entities", "home", "Chủ thể OCOP"),
                                        ("/ocop/applications", "file", "Hồ sơ đánh giá"),
                                        ("/ocop/criteria", "table", "Bộ tiêu chí")]))
        nav_groups.append(("HỆ THỐNG", system_items))
        nav = [sidebar_group(group, items, current) for group, items in nav_groups]
        name = account_display_name(session)
        display_label = esc(name)
        if name == "CHI CỤC PHÁT TRIỂN NÔNG THÔN THÀNH PHỐ HỒ CHÍ MINH":
            display_label = 'CHI CỤC PHÁT TRIỂN NÔNG THÔN<br>THÀNH PHỐ HỒ CHÍ MINH'
        role_label = ROLE_LABELS[session["role"]]
        initial = esc((session['username'] or 'U')[0].upper())
        top = f"""
        <a class="skip-link" href="#main-content">Đến nội dung chính</a>
        <header class="site-header">
          <button class="menu-toggle" id="sidebar-toggle" type="button" aria-label="Thu gọn menu" aria-expanded="true" aria-controls="site-sidebar">{icon('menu')}</button>
          <a class="brand-link" href="/dashboard">
            <img class="brand-emblem" src="/assets/quoc-huy.png" alt="Quốc huy Việt Nam" width="56" height="58">
            <div class="brand-copy"><div class="brand-agency">{display_label}</div><div class="brand-subtitle">HỆ THỐNG QUẢN LÝ NGHIỆP VỤ</div></div>
          </a>
          <div class="header-tools">
            <div class="header-clock"><time class="clock-time" id="clock-time">{datetime.now().strftime('%H:%M:%S')}</time><div class="clock-date" id="clock-date">{date.today().strftime('%d/%m/%Y')}</div></div>
            <div class="header-account"><div class="account-copy"><div class="account-name">{esc(session['username'])}</div><div class="account-role">{role_label}</div><a class="account-logout" href="/logout">Đăng xuất</a></div><span class="account-avatar" aria-hidden="true">{initial}</span></div>
          </div>
        </header>
        <aside class="sidebar" id="site-sidebar" aria-label="Menu chính">
          <form class="sidebar-search" action="/records" method="get" role="search"><button type="submit" aria-label="Tìm báo cáo muối">{icon('search')}</button><input name="q" type="search" placeholder="Tìm báo cáo muối..." aria-label="Tìm báo cáo muối theo đơn vị hoặc ghi chú"></form>
          <nav class="sidebar-nav" aria-label="Chức năng">{''.join(nav)}</nav>
          <div class="sidebar-footer"><img class="sidebar-watermark" src="/assets/quoc-huy.png" alt="" width="148" height="152"><div class="sidebar-footer-line"></div><strong><span>TRUNG TÂM CHUYỂN ĐỔI SỐ</span><span>NÔNG NGHIỆP VÀ MÔI TRƯỜNG</span></strong><p>Theo dõi sản xuất và tổng hợp báo cáo các đơn vị.</p></div>
        </aside>
        <button type="button" id="sidebar-backdrop" class="sidebar-backdrop" aria-label="Đóng menu" tabindex="-1"></button>
        """
        body = f'<main class="app-main" id="main-content">{body}</main>'
    return f"""<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)} · Quản lý nghiệp vụ</title><link rel="icon" href="/assets/quoc-huy.png" type="image/png"><link rel="stylesheet" href="/assets/app.css?v=20260910-weekly-tabs"><script src="/assets/app.js?v=20260910-import-status" defer></script></head><body>{top}{body}</body></html>"""


def login_page(message=""):
    notice = f'<div class="notice err">{esc(message)}</div>' if message else ""
    body = f"""
    <div class="login-wrap"><div class="login">
      <img class="login-emblem" src="/assets/quoc-huy.png" alt="Quốc huy Việt Nam" width="70" height="72">
      <h1>Hệ thống quản lý nghiệp vụ</h1>
      <p>Chi cục Phát triển nông thôn và các đơn vị xã/phường.</p>
      {notice}
      <form method="post" action="/login">
        <div class="field"><label>Tên đăng nhập</label><input name="username" autocomplete="username" required autofocus></div>
        <div class="field"><label>Mật khẩu</label><input type="password" name="password" autocomplete="current-password" required></div>
        <button class="btn primary" style="width:100%;margin-top:6px">Đăng nhập</button>
      </form>
      <div class="notice info" style="margin-top:16px"><b>Tài khoản demo:</b> chicuc / 123456<br>Đơn vị ví dụ: an_thoi_dong / 123456<br><b>Đổi mật khẩu ngay khi triển khai thật.</b></div>
    </div></div>
    """
    return base_page("Đăng nhập", body)


def filters_from_query(query, session):
    params = parse_qs(query)
    filters = {
        "q": params.get("q", [""])[0].strip(),
        "unit": params.get("unit", [""])[0].strip(),
        "status": params.get("status", [""])[0].strip(),
        "from": params.get("from", [""])[0].strip(),
        "to": params.get("to", [""])[0].strip(),
    }
    if session["role"] == ROLE_UNIT:
        filters["unit"] = session["unit_name"]
    return filters


def fetch_records(con, session, filters):
    sql = "SELECT r.*, u.username creator_username FROM records r JOIN users u ON u.id=r.created_by WHERE 1=1"
    args = []
    if session["role"] == ROLE_UNIT:
        sql += " AND r.unit_name=?"
        args.append(session["unit_name"])
    elif filters.get("unit"):
        sql += " AND r.unit_name=?"
        args.append(filters["unit"])
    if filters.get("status"):
        sql += " AND r.status=?"
        args.append(filters["status"])
    if filters.get("from"):
        sql += " AND r.report_date>=?"
        args.append(filters["from"])
    if filters.get("to"):
        sql += " AND r.report_date<=?"
        args.append(filters["to"])
    if filters.get("q"):
        sql += " AND (r.unit_name LIKE ? OR r.note LIKE ? OR r.reviewer_note LIKE ?)"
        q = f"%{filters['q']}%"
        args.extend([q, q, q])
    sql += " ORDER BY r.report_date DESC, r.unit_name ASC"
    return con.execute(sql, args).fetchall()


def get_units(con):
    return [r[0] for r in con.execute("SELECT DISTINCT unit_name FROM users WHERE role='unit' AND active=1 AND unit_name IS NOT NULL ORDER BY unit_name").fetchall()]


def dashboard_page(session, query=""):
    """Dashboard for effective weekly records, compared with a distinct earlier week."""
    official = canonical_admin_unit(session["unit_name"]) if session["role"] == ROLE_UNIT else None
    params = parse_qs(query)
    con = db_conn()
    try:
        data = effective_weekly_dashboard(
            con, week=params.get("week", [""])[0].strip(),
            batch=params.get("batch", [""])[0].strip(),
            unit_code=(official[1] if official else "") if session["role"] == ROLE_UNIT else None)
    finally:
        con.close()
    if data is None:
        return legacy_dashboard_page(session)
    periods, selected, previous = data["periods"], data["selected"], data["previous"]
    rows, previous_rows = data["rows"], data["previous_rows"]

    def sums(source):
        return {
            key: sum(float(row.get(key) or 0) for row in source)
            for key in ("dien_tich", "san_luong", "sold_total", "remaining_total",
                        "area_land", "area_tarp", "harvest_land", "harvest_tarp",
                        "sold_land", "sold_tarp", "remaining_land", "remaining_tarp",
                        "households", "workers")
        }

    current_totals, previous_totals = sums(rows), sums(previous_rows)
    period_label = date.fromisoformat(str(selected["report_date"])).strftime("%d/%m/%Y")
    previous_label = (previous["week_code"] + " · " + date.fromisoformat(str(previous["report_date"])).strftime("%d/%m/%Y")
                      if previous else "chưa có kỳ trước")

    def metric_panel(label, total_key, land_key, tarp_key, unit, symbol, amber=False):
        total = current_totals[total_key]
        before = previous_totals[total_key]
        difference = total - before
        tone = " amber" if amber else ""
        if previous:
            marker = "+" if difference > 0 else ""
            delta = f'<div class="metric-delta"><strong>{marker}{fmt_num(difference)}</strong> {esc(unit)} so với {esc(previous_label)}</div>'
        else:
            delta = '<div class="metric-delta muted">Chưa có tuần trước để so sánh</div>'
        return f"""<article class="metric-panel{tone}">
          <div class="metric-top"><h3>{label}</h3>{icon(symbol)}</div>
          <div class="metric-middle"><div><div class="metric-number">{fmt_num(total)}</div><div class="metric-caption">{unit} · lũy tiến đến {esc(period_label)}</div>{delta}</div><div class="metric-symbol">{icon(symbol)}</div></div>
          <div class="metric-breakdown"><div><span>Muối đất</span><strong>{fmt_num(current_totals[land_key])} <small>{unit}</small></strong></div><div><span>Muối trải bạt</span><strong>{fmt_num(current_totals[tarp_key])} <small>{unit}</small></strong></div></div>
        </article>"""

    metrics = ''.join([
        metric_panel('DIỆN TÍCH SẢN XUẤT MUỐI', 'dien_tich', 'area_land', 'area_tarp', 'ha', 'area'),
        metric_panel('SẢN LƯỢNG MUỐI THU HOẠCH', 'san_luong', 'harvest_land', 'harvest_tarp', 'tấn', 'harvest'),
        metric_panel('SẢN LƯỢNG MUỐI TIÊU THỤ', 'sold_total', 'sold_land', 'sold_tarp', 'tấn', 'sold', True),
        metric_panel('SẢN LƯỢNG MUỐI CÒN LẠI', 'remaining_total', 'remaining_land', 'remaining_tarp', 'tấn', 'stock', True),
    ])
    options = ''.join(
        f'<option value="{period["week_code"]}" {"selected" if period["week_code"] == selected["week_code"] else ""}>'
        f'{esc(period["week_code"])}</option>'
        for period in periods
    )
    status_cards = ''.join([
        f'<a class="status-card draft" href="/salt/weekly"><span class="status-icon">{icon("file")}</span><div><div class="status-card-count">{len(periods)}</div><div class="status-card-label">Tuần có dữ liệu</div></div></a>',
        f'<a class="status-card approved" href="/salt/weekly?week={selected["week_code"]}"><span class="status-icon">{icon("check")}</span><div><div class="status-card-count">{len(rows)}</div><div class="status-card-label">Đơn vị trong kỳ</div></div></a>',
        f'<a class="status-card submitted" href="/salt/weekly?week={selected["week_code"]}"><span class="status-icon">{icon("chart")}</span><div><div class="status-card-count">{data["warning_rows"]}</div><div class="status-card-label">Dòng cảnh báo</div></div></a>',
        f'<a class="status-card returned" href="/salt/weekly?week={previous["week_code"] if previous else selected["week_code"]}"><span class="status-icon">{icon("return")}</span><div><div class="status-card-count">{previous["week_code"] if previous else "—"}</div><div class="status-card-label">Kỳ dùng để so sánh</div></div></a>',
    ])
    summary_rows = ''.join(
        f'<tr><td>{esc(row["unit_name"])}</td><td>{fmt_num(row["dien_tich"])}</td><td>{fmt_num(row["san_luong"])}</td><td>{fmt_num(row["sold_total"])}</td><td>{fmt_num(row["remaining_total"])}</td><td>{fmt_num(row["households"])}</td><td>{fmt_num(row["workers"])}</td></tr>'
        for row in sorted(rows, key=lambda item: item["unit_name"])
    ) or '<tr><td colspan="7" class="empty">Đơn vị này chưa có dữ liệu trong tuần.</td></tr>'
    scope = "Tất cả đơn vị" if is_chi_cuc_user(session) else session["unit_name"]
    body = f"""
    <div class="container">
      {take_flash(session)}
      <div class="page-head"><div><h1>Bảng giám sát</h1><div class="subtitle">Số liệu lũy tiến có hiệu lực của tuần và mức thay đổi so với tuần có dữ liệu gần nhất trước đó.</div></div><a class="btn primary" href="/import-excel">{icon('download')}Import báo cáo tuần</a></div>
      <div class="dashboard-toolbar"><form class="dashboard-period" method="get"><div class="field"><label>Kỳ đang xem</label><select name="week">{options}</select></div><button class="btn primary">Xem dashboard</button></form><div class="scope-label">{icon('location')}<span>Đơn vị: <strong>{esc(scope)}</strong></span></div></div>
      <div class="status-overview" aria-label="Tình trạng báo cáo tuần">{status_cards}</div>
      <section class="dashboard-panel">
        <div class="panel-heading"><h2 class="panel-title"><span class="panel-title-icon">{icon('chart')}</span>SỐ LIỆU SẢN XUẤT MUỐI</h2><div class="panel-meta">{esc(selected['week_code'])}<br>So sánh với: {esc(previous['week_code']) if previous else 'Chưa có tuần trước'}</div></div>
        <div class="dashboard-metrics">{metrics}</div>
        <div class="people-metrics"><div class="people-card"><div><div class="label">Số hộ làm muối</div><div class="value">{fmt_num(current_totals['households'])} <small>hộ</small></div></div>{icon('home')}</div><div class="people-card"><div><div class="label">Lao động làm muối</div><div class="value">{fmt_num(current_totals['workers'])} <small>người</small></div></div>{icon('users')}</div></div>
        <p class="dashboard-note">Số liệu có hiệu lực của tuần đang chọn. Chênh lệch bằng tuần đang xem trừ tuần có dữ liệu gần nhất trước đó; các lần upload cùng tuần không tạo thêm kỳ so sánh.</p>
      </section>
      <section class="dashboard-panel"><div class="panel-heading"><h2 class="panel-title"><span class="panel-title-icon">{icon('table')}</span>CHI TIẾT THEO ĐƠN VỊ</h2><a class="btn small" href="/salt/weekly?week={selected['week_code']}">Lịch sử Excel của tuần</a></div><div class="table-wrap"><table class="summary-table"><thead><tr><th>Đơn vị</th><th>Diện tích (ha)</th><th>Thu hoạch (tấn)</th><th>Tiêu thụ (tấn)</th><th>Còn lại (tấn)</th><th>Số hộ</th><th>Lao động</th></tr></thead><tbody>{summary_rows}</tbody></table></div></section>
    </div>"""
    return base_page("Tổng quan", body, session)


def legacy_dashboard_page(session):
    con = db_conn()
    if is_chi_cuc_user(session):
        approved_rows = con.execute("SELECT * FROM records WHERE status='approved' ORDER BY report_date DESC, id DESC").fetchall()
        status_counts = {s: con.execute("SELECT COUNT(*) FROM records WHERE status=?", (s,)).fetchone()[0] for s in STATUS_LABELS}
        standard_rows = con.execute(
            """SELECT s.*, d.TenDonVi unit_name
               FROM DN_SanLuongMuoi s
               LEFT JOIN DM_DonViHanhChinh d
                 ON d.Ma_DonViHanhChinh=s.Ma_DonViHanhChinh"""
        ).fetchall()
    else:
        approved_rows = con.execute("SELECT * FROM records WHERE unit_name=? AND status='approved' ORDER BY report_date DESC, id DESC", (session["unit_name"],)).fetchall()
        status_counts = {s: con.execute("SELECT COUNT(*) FROM records WHERE unit_name=? AND status=?", (session["unit_name"], s)).fetchone()[0] for s in STATUS_LABELS}
        standard_rows = con.execute(
            """SELECT s.*, d.TenDonVi unit_name
               FROM DN_SanLuongMuoi s
               JOIN DM_DonViHanhChinh d
                 ON d.Ma_DonViHanhChinh=s.Ma_DonViHanhChinh
               WHERE d.TenDonVi=?""",
            (session["unit_name"],),
        ).fetchall()

    # Operational details are kept in app.records. Use only the latest
    # cumulative report per unit/month so weekly cumulative reports are not
    # added together. Official area/production below always come from QD 5277.
    rows = []
    seen_periods = set()
    for row in approved_rows:
        if row["reporting_mode"] != "cumulative":
            continue
        key = (row["unit_name"], str(row["report_date"])[:7])
        if key not in seen_periods:
            seen_periods.add(key)
            rows.append(row)

    totals = {"area_total":0,"harvest_total":0,"sold_total":0,"remaining_total":0,"households":0,"workers":0}
    for r in rows:
        t = record_totals(r)
        totals["sold_total"] += t["sold_total"]
        totals["remaining_total"] += t["remaining_total"]
        totals["households"] += r["households"] or 0
        totals["workers"] += r["workers"] or 0
    totals["area_total"] = sum(float(r["DienTich"] or 0) for r in standard_rows)
    totals["harvest_total"] = sum(float(r["SanLuong"] or 0) for r in standard_rows)

    if is_chi_cuc_user(session):
        summaries = {}
        for r in standard_rows:
            name = r["unit_name"] or r["Ma_DonViHanhChinh"]
            item = summaries.setdefault(name, {"unit_name":name, "area_total":0,
                "harvest_total":0, "sold_total":0, "remaining_total":0,
                "households":0, "workers":0, "periods":set()})
            item["area_total"] += float(r["DienTich"] or 0)
            item["harvest_total"] += float(r["SanLuong"] or 0)
            item["periods"].add(str(r["Ma_ThoiGian"]))
        for r in rows:
            item = summaries.setdefault(r["unit_name"], {"unit_name":r["unit_name"],
                "area_total":0, "harvest_total":0, "sold_total":0,
                "remaining_total":0, "households":0, "workers":0, "periods":set()})
            detail = record_totals(r)
            item["sold_total"] += float(detail["sold_total"] or 0)
            item["remaining_total"] += float(detail["remaining_total"] or 0)
            item["households"] += float(r["households"] or 0)
            item["workers"] += float(r["workers"] or 0)
            item["periods"].add(str(r["report_date"])[:7])
        unit_summary = []
        for item in summaries.values():
            item["reports"] = len(item.pop("periods"))
            unit_summary.append(item)
        unit_summary.sort(key=lambda item: item["unit_name"])
    else:
        unit_summary = []
    con.close()

    breakdowns = {
        key: sum(float(r[key] or 0) for r in rows)
        for key in ('area_land', 'area_tarp', 'harvest_land', 'harvest_tarp',
                    'sold_land', 'sold_tarp', 'remaining_land', 'remaining_tarp')
    }

    def metric_panel(label, total_key, land_key, tarp_key, unit, symbol, amber=False):
        total = float(totals[total_key] or 0)
        land, tarp = breakdowns[land_key], breakdowns[tarp_key]
        tone = ' amber' if amber else ''
        if amber:
            share = max(0, min(100, land / total * 100)) if total > 0 else 0
            share_label = f'{fmt_num(share, 1)}%' if total > 0 else '—'
            visual = f'<div class="donut" style="--share:{share:.2f}%" role="img" aria-label="Tỷ trọng muối đất: {share_label}"><div class="donut-label"><strong>{share_label}</strong><small>Muối đất</small></div></div>'
        else:
            visual = f'<div class="metric-symbol">{icon(symbol)}</div>'
        return f"""<article class="metric-panel{tone}">
          <div class="metric-top"><h3>{label}</h3>{icon(symbol)}</div>
          <div class="metric-middle"><div><div class="metric-number">{fmt_num(total)}</div><div class="metric-caption">{unit} · tổng số đã duyệt</div></div>{visual}</div>
          <div class="metric-breakdown"><div><span>Muối đất</span><strong>{fmt_num(land)} <small>{unit}</small></strong></div><div><span>Muối trải bạt</span><strong>{fmt_num(tarp)} <small>{unit}</small></strong></div></div>
        </article>"""

    metrics = ''.join([
        metric_panel('DIỆN TÍCH SẢN XUẤT MUỐI', 'area_total', 'area_land', 'area_tarp', 'ha', 'area'),
        metric_panel('SẢN LƯỢNG MUỐI THU HOẠCH', 'harvest_total', 'harvest_land', 'harvest_tarp', 'tấn', 'harvest'),
        metric_panel('SẢN LƯỢNG MUỐI TIÊU THỤ', 'sold_total', 'sold_land', 'sold_tarp', 'tấn', 'sold', True),
        metric_panel('SẢN LƯỢNG MUỐI CÒN LẠI', 'remaining_total', 'remaining_land', 'remaining_tarp', 'tấn', 'stock', True),
    ])
    status_symbols = {'draft':'file', 'submitted':'send', 'approved':'check', 'returned':'return'}
    status_short = {'draft':'Bản nháp', 'submitted':'Chờ Chi cục duyệt', 'approved':'Đã duyệt', 'returned':'Cần chỉnh sửa'}
    statuses = ''.join(
        f'<a class="status-card {state}" href="/records?status={state}"><span class="status-icon">{icon(status_symbols[state])}</span><div><div class="status-card-count">{status_counts[state]}</div><div class="status-card-label">{status_short[state]}</div></div></a>'
        for state in STATUS_LABELS
    )
    scope = 'Tất cả đơn vị' if is_chi_cuc_user(session) else session['unit_name']
    latest = max((r['updated_at'] for r in rows), default='')
    updated_label = f'Cập nhật báo cáo: {esc(latest)}' if latest else 'Chưa có báo cáo được duyệt'
    summary_html = ''
    if is_chi_cuc_user(session):
        if unit_summary:
            rows_html = ''.join(
                f"<tr><td>{esc(r['unit_name'])}</td><td>{fmt_num(r['area_total'])}</td><td>{fmt_num(r['harvest_total'])}</td><td>{fmt_num(r['sold_total'])}</td><td>{fmt_num(r['remaining_total'])}</td><td>{fmt_num(r['households'])}</td><td>{fmt_num(r['workers'])}</td><td>{r['reports']}</td></tr>"
                for r in unit_summary
            )
            summary_content = f'<div class="table-wrap"><table class="summary-table"><thead><tr><th>Đơn vị</th><th>Diện tích (ha)</th><th>Thu hoạch (tấn)</th><th>Tiêu thụ (tấn)</th><th>Còn lại (tấn)</th><th>Số hộ</th><th>Lao động</th><th>Số kỳ</th></tr></thead><tbody>{rows_html}</tbody></table></div>'
        else:
            summary_content = f'<div class="summary-empty">{icon("table")}<div><strong>Chưa có số liệu để tổng hợp</strong><p>Báo cáo của các đơn vị sẽ xuất hiện tại đây sau khi được Chi cục duyệt.</p></div></div>'
        summary_html = f'<section class="dashboard-panel"><div class="panel-heading"><h2 class="panel-title"><span class="panel-title-icon">{icon("table")}</span>TỔNG HỢP THEO ĐƠN VỊ</h2><a class="btn small" href="/records?status=approved">Xem báo cáo</a></div>{summary_content}</section>'

    body = f"""
    <div class="container">
      {take_flash(session)}
      <div class="page-head"><div><h1>Bảng giám sát</h1><div class="subtitle">Theo dõi số liệu sản xuất muối và tình trạng báo cáo.</div></div><a class="btn primary" href="/records/new">{icon('plus')}Nhập số liệu</a></div>
      <div class="dashboard-toolbar"><nav class="view-tabs" aria-label="Chế độ xem"><a class="view-tab active" href="/dashboard" aria-current="page">Tổng quan</a><a class="view-tab" href="/records">Dữ liệu chi tiết</a></nav><div class="scope-label">{icon('location')}<span>Đơn vị: <strong>{esc(scope)}</strong></span></div></div>
      <div class="status-overview" aria-label="Tình trạng báo cáo">{statuses}</div>
      <section class="dashboard-panel">
        <div class="panel-heading"><h2 class="panel-title"><span class="panel-title-icon">{icon('chart')}</span>SỐ LIỆU SẢN XUẤT MUỐI</h2><div class="panel-meta">{len(rows)} báo cáo đã duyệt · Tất cả kỳ báo cáo<br>{updated_label}</div></div>
        <div class="dashboard-metrics">{metrics}</div>
        <div class="people-metrics"><div class="people-card"><div><div class="label">Số hộ làm muối</div><div class="value">{fmt_num(totals['households'])} <small>hộ</small></div></div>{icon('home')}</div><div class="people-card"><div><div class="label">Lao động làm muối</div><div class="value">{fmt_num(totals['workers'])} <small>người</small></div></div>{icon('users')}</div></div>
        <p class="dashboard-note">Các chỉ tiêu được cộng từ tất cả báo cáo đã duyệt; số hộ và lao động có thể lặp lại giữa các kỳ.</p>
      </section>
      {summary_html}
      <div class="actions"><a class="btn" href="/export.xlsx?status=approved">{icon('download')}Xuất Excel số liệu đã duyệt</a><a class="btn" href="/records">Tra cứu báo cáo</a></div>
    </div>
    """
    return base_page("Tổng quan", body, session)


def record_action_buttons(session, r):
    actions = [f'<a class="btn small" href="/records/{r["id"]}">Xem</a>']
    if is_chi_cuc_user(session):
        actions.append(f'<a class="btn small" href="/records/{r["id"]}/edit">Sửa</a>')
        if r["status"] == STATUS_SUBMITTED:
            actions.append(f'<form style="display:inline" method="post" action="/records/{r["id"]}/approve">{csrf_input(session)}<button class="btn small ok">Duyệt</button></form>')
            actions.append(f'<a class="btn small warn" href="/records/{r["id"]}/return">Trả chỉnh sửa</a>')
    else:
        if r["status"] in (STATUS_DRAFT, STATUS_RETURNED):
            actions.append(f'<a class="btn small" href="/records/{r["id"]}/edit">Sửa</a>')
            actions.append(f'<form style="display:inline" method="post" action="/records/{r["id"]}/submit">{csrf_input(session)}<button class="btn small primary">Gửi Chi cục</button></form>')
    return '<div class="actions">' + ''.join(actions) + '</div>'


def records_page(session, query):
    filters = filters_from_query(query, session)
    con = db_conn()
    records = fetch_records(con, session, filters)
    units = get_units(con)
    con.close()

    unit_options = '<option value="">Tất cả đơn vị</option>' + ''.join(f'<option value="{esc(u)}" {"selected" if u==filters["unit"] else ""}>{esc(u)}</option>' for u in units)
    status_options = '<option value="">Tất cả trạng thái</option>' + ''.join(f'<option value="{s}" {"selected" if s==filters["status"] else ""}>{STATUS_LABELS[s]}</option>' for s in STATUS_LABELS)
    unit_field = '' if session["role"] == ROLE_UNIT else f'<div class="field"><label>Đơn vị</label><select name="unit">{unit_options}</select></div>'

    trs = []
    for r in records:
        t = record_totals(r)
        trs.append(f"""
        <tr>
          <td>{esc(r['report_date'])}</td><td>{esc(r['unit_name'])}</td><td><span class="status {esc(r['status'])}">{STATUS_LABELS[r['status']]}</span></td>
          <td>{fmt_num(t['area_total'])}</td><td>{fmt_num(t['harvest_total'])}</td><td>{fmt_num(t['sold_total'])}</td><td>{fmt_num(t['remaining_total'])}</td><td>{fmt_num(r['households'])}</td><td>{fmt_num(r['workers'])}</td><td>{fmt_num(t['avg_yield'],2)}</td>
          <td>{record_action_buttons(session,r)}</td>
        </tr>""")
    table_body = ''.join(trs) if trs else '<tr><td colspan="11" class="empty">Chưa có dữ liệu phù hợp.</td></tr>'

    query_string = '&'.join(f"{quote(k)}={quote(v)}" for k,v in filters.items() if v)
    standard_button = '<a class="btn" href="/standard-data">Dữ liệu chuẩn hóa</a>' if is_chi_cuc_user(session) else ''
    body = f"""
    <div class="container">
      {take_flash(session)}
      <div class="page-head"><div><h1>Dữ liệu báo cáo</h1><div class="subtitle">Tra cứu, lọc và xuất dữ liệu theo kỳ báo cáo/đơn vị/trạng thái.</div></div><div class="actions"><a class="btn primary" href="/records/new">+ Nhập số liệu</a><a class="btn ok" href="/export.xlsx?{query_string}">Xuất Excel</a>{standard_button}</div></div>
      {salt_data_tabs(session, "/records")}
      <div class="card"><form class="toolbar" method="get" action="/records">
        <div class="field"><label>Từ khóa</label><input name="q" value="{esc(filters['q'])}" placeholder="Đơn vị, ghi chú..."></div>
        {unit_field}
        <div class="field"><label>Trạng thái</label><select name="status">{status_options}</select></div>
        <div class="field"><label>Từ ngày</label><input type="date" name="from" value="{esc(filters['from'])}"></div>
        <div class="field"><label>Đến ngày</label><input type="date" name="to" value="{esc(filters['to'])}"></div>
        <button class="btn primary">Tra cứu</button><a class="btn" href="/records">Xóa lọc</a>
      </form></div>
      <div class="card"><div class="table-wrap"><table class="table"><thead><tr><th>Kỳ báo cáo</th><th>Đơn vị</th><th>Trạng thái</th><th>Diện tích (ha)</th><th>Thu hoạch (tấn)</th><th>Tiêu thụ (tấn)</th><th>Còn lại (tấn)</th><th>Số hộ</th><th>Lao động</th><th>Năng suất BQ</th><th>Thao tác</th></tr></thead><tbody>{table_body}</tbody></table></div></div>
    </div>
    """
    return base_page("Dữ liệu báo cáo", body, session)


def standard_data_page(session):
    if not is_chi_cuc_user(session):
        return None

    con = db_conn()
    rows = con.execute(
        """
        SELECT
            s.Ma_SanLuongMuoi,
            s.Ma_DonViHanhChinh,
            d.TenDonVi,
            s.Ma_ThoiGian,
            s.PhuongPhapSX,
            s.DienTich,
            s.SanLuong,
            s.GiaBanBinhQuan
        FROM DN_SanLuongMuoi s
        LEFT JOIN DM_DonViHanhChinh d
               ON d.Ma_DonViHanhChinh = s.Ma_DonViHanhChinh
        ORDER BY s.Ma_ThoiGian DESC, d.TenDonVi ASC, s.PhuongPhapSX ASC
        """
    ).fetchall()
    con.close()

    def display_time(code):
        text = str(code or "")
        if len(text) == 8 and text.isdigit():
            return f"{text[6:8]}/{text[4:6]}/{text[0:4]}"
        return text

    trs = []
    for r in rows:
        code_class = "muted" if str(r["Ma_DonViHanhChinh"] or "").startswith("TMP") else ""
        trs.append(f"""
        <tr>
          <td>{r['Ma_SanLuongMuoi']}</td>
          <td><span class="{code_class}">{esc(r['Ma_DonViHanhChinh'])}</span></td>
          <td>{esc(r['TenDonVi'] or '')}</td>
          <td>{esc(display_time(r['Ma_ThoiGian']))}</td>
          <td>{esc(r['PhuongPhapSX'])}</td>
          <td>{fmt_num(r['DienTich'], 2)}</td>
          <td>{fmt_num(r['SanLuong'], 2)}</td>
          <td>{fmt_num(r['GiaBanBinhQuan'], 2)}</td>
        </tr>
        """)

    table_body = ''.join(trs) if trs else '<tr><td colspan="8" class="empty">Chưa có báo cáo tháng được duyệt để xuất bản theo QĐ 5277.</td></tr>'

    body = f"""
    <div class="container">
      {take_flash(session)}
      <div class="page-head">
        <div>
          <h1>Dữ liệu chuẩn hóa</h1>
          <div class="subtitle">
            Dữ liệu báo cáo tháng đã duyệt, xuất bản theo cấu trúc DN_SanLuongMuoi của QĐ 5277.
          </div>
        </div>
        <div class="actions">
          <a class="btn" href="/records">← Dữ liệu báo cáo</a>
        </div>
      </div>

      {salt_data_tabs(session, "/standard-data")}

      <div class="notice info">
        Tổng cộng <b>{len(rows)}</b> bản ghi chuẩn hóa. Sheet tuần chỉ dùng cho theo dõi và so sánh;
        chưa tự ghi vào đây để tránh hiểu số liệu lũy tiến tuần thành báo cáo tháng.
      </div>

      <div class="card">
        <div class="table-wrap">
          <table class="summary-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Mã đơn vị</th>
                <th>Đơn vị</th>
                <th>Kỳ số liệu</th>
                <th>Phương pháp SX</th>
                <th>Diện tích (ha)</th>
                <th>Sản lượng (tấn)</th>
                <th>Giá bán BQ (đ/kg)</th>
              </tr>
            </thead>
            <tbody>{table_body}</tbody>
          </table>
        </div>
      </div>
    </div>
    """
    return base_page("Dữ liệu chuẩn hóa", body, session)


def input_field(name, label, value="", typ="number", step="0.1", extra=""):
    attrs = f'type="{typ}" name="{name}" value="{esc(value)}"'
    if typ == "number":
        attrs += f' min="0" step="{step}"'
    return f'<div class="field"><label>{esc(label)}</label><input {attrs} {extra}></div>'


def record_form_page(session, record=None, error=""):
    con = db_conn()
    units = get_units(con)
    con.close()
    is_edit = record is not None
    v = lambda key, default="": record[key] if record is not None and key in record.keys() else default
    unit_name = session["unit_name"] if session["role"] == ROLE_UNIT else v("unit_name", units[0] if units else "")
    unit_select = ''.join(f'<option value="{esc(u)}" {"selected" if u==unit_name else ""}>{esc(u)}</option>' for u in units)
    unit_html = f'<div class="field"><label>Đơn vị xã/phường</label><select name="unit_name" required>{unit_select}</select></div>' if is_chi_cuc_user(session) else f'<div class="field"><label>Đơn vị xã/phường</label><input value="{esc(unit_name)}" readonly></div><input type="hidden" name="unit_name" value="{esc(unit_name)}">'
    action = f'/records/{record["id"]}/edit' if is_edit else '/records/new'
    notice = f'<div class="notice err">{esc(error)}</div>' if error else ''
    reviewer = ""
    if is_edit and v("reviewer_note"):
        reviewer = f'<div class="notice info"><b>Ý kiến Chi cục:</b> {esc(v("reviewer_note"))}</div>'
    body = f"""
    <div class="container">
      <div class="page-head">
        <div>
          <h1>{'Cập nhật' if is_edit else 'Nhập'} số liệu</h1>
          <div class="subtitle">Các cột “Cộng” và “Năng suất bình quân” được hệ thống tự tính.</div>
        </div>
        <div class="actions">
          <a class="btn ok" href="/import-excel">{icon('download')} Nhập dữ liệu từ Excel</a>
          <a class="btn" href="/records">← Danh sách</a>
        </div>
      </div>
      {notice}{reviewer}
      <form class="card" method="post" action="{action}">{csrf_input(session)}
        <div class="grid">
          <div class="field"><label>Ngày/kỳ chốt số liệu</label><input type="date" name="report_date" value="{esc(v('report_date', date.today().isoformat()))}" required></div>
          {unit_html}
        </div>

        <div class="section-title">1. Diện tích sản xuất muối (ha)</div><div class="grid">
          {input_field('area_land','Muối đất',v('area_land',0))}
          {input_field('area_tarp','Muối trải bạt',v('area_tarp',0))}
          <div class="field"><label>Cộng (tự tính)</label><input class="calc" id="area_total" readonly></div>
        </div>

        <div class="section-title">2. Sản lượng muối thu hoạch (tấn)</div><div class="grid">
          {input_field('harvest_land','Muối đất',v('harvest_land',0))}
          {input_field('harvest_tarp','Muối trải bạt',v('harvest_tarp',0))}
          <div class="field"><label>Cộng (tự tính)</label><input class="calc" id="harvest_total" readonly></div>
        </div>

        <div class="section-title">3. Sản lượng muối tiêu thụ (tấn)</div><div class="grid">
          {input_field('sold_land','Muối đất',v('sold_land',0))}
          {input_field('sold_tarp','Muối trải bạt',v('sold_tarp',0))}
          <div class="field"><label>Cộng (tự tính)</label><input class="calc" id="sold_total" readonly></div>
        </div>

        <div class="section-title">4. Sản lượng còn lại (tấn)</div><div class="grid">
          {input_field('remaining_land','Muối đất',v('remaining_land',0))}
          {input_field('remaining_tarp','Muối trải bạt',v('remaining_tarp',0))}
          <div class="field"><label>Cộng (tự tính)</label><input class="calc" id="remaining_total" readonly></div>
        </div>

        <div class="section-title">5. Sản lượng muối chế biến (tấn)</div><div class="grid">
          {input_field('processed_fine','Muối tinh',v('processed_fine',0))}
          {input_field('processed_iodized','Muối I-ốt',v('processed_iodized',0))}
          <div class="field"><label>Cộng (tự tính)</label><input class="calc" id="processed_total" readonly></div>
        </div>

        <div class="section-title">6. Hộ, lao động, giá bán và năng suất</div><div class="grid">
          {input_field('households','Số hộ làm muối (hộ)',v('households',0),'number','1')}
          {input_field('workers','Số lao động làm muối (người)',v('workers',0),'number','1')}
          {input_field('price_land','Giá bán muối đất (đồng/kg)',v('price_land',''),'text','','placeholder="Ví dụ 1.000 - 1.500"')}
          {input_field('price_tarp','Giá bán muối trải bạt (đồng/kg)',v('price_tarp',''),'text','','placeholder="Ví dụ 1.200 - 1.800"')}
          <div class="field"><label>Năng suất BQ (tấn/ha, tự tính)</label><input class="calc" id="avg_yield" readonly></div>
        </div>

        <div class="section-title">7. Thiệt hại do mưa trái mùa (tấn)</div><div class="grid">
          {input_field('damage_land','Muối đất',v('damage_land',0))}
          {input_field('damage_tarp','Muối trải bạt',v('damage_tarp',0))}
          <div class="field"><label>Cộng (tự tính)</label><input class="calc" id="damage_total" readonly></div>
        </div>

        <div class="section-title">8. Ghi chú</div><div class="field"><textarea name="note" placeholder="Ghi chú, giải trình số liệu...">{esc(v('note',''))}</textarea></div>
        <div class="actions" style="margin-top:16px"><button class="btn primary">Lưu dữ liệu</button><a class="btn" href="/records">Hủy</a></div>
      </form>
    </div>
    <script>
    function n(name){{const e=document.querySelector('[name="'+name+'"]'); return e?parseFloat((e.value||'0').replace(',','.'))||0:0;}}
    function calc(){{
      const pairs=[['area_land','area_tarp','area_total'],['harvest_land','harvest_tarp','harvest_total'],['sold_land','sold_tarp','sold_total'],['remaining_land','remaining_tarp','remaining_total'],['processed_fine','processed_iodized','processed_total'],['damage_land','damage_tarp','damage_total']];
      pairs.forEach(p=>document.getElementById(p[2]).value=(n(p[0])+n(p[1])).toFixed(1));
      const a=n('area_land')+n('area_tarp'), h=n('harvest_land')+n('harvest_tarp');
      document.getElementById('avg_yield').value=a?(h/a).toFixed(2):'0.00';
    }}
    document.querySelectorAll('input[type="number"]').forEach(e=>e.addEventListener('input',calc)); calc();
    </script>
    """
    return base_page("Nhập số liệu", body, session)


def can_access_record(session, r):
    return is_chi_cuc_user(session) or r["unit_name"] == session["unit_name"]


def detail_page(session, rid):
    con = db_conn()
    r = con.execute("SELECT * FROM records WHERE id=?", (rid,)).fetchone()
    if not r or not can_access_record(session, r):
        con.close(); return None
    logs = con.execute("SELECT a.*, u.username FROM audit_logs a LEFT JOIN users u ON u.id=a.user_id WHERE record_id=? ORDER BY a.id DESC", (rid,)).fetchall()
    con.close()
    t = record_totals(r)
    rows = [
        ("Diện tích sản xuất muối (ha)", t["area_total"], r["area_land"], r["area_tarp"]),
        ("Sản lượng thu hoạch (tấn)", t["harvest_total"], r["harvest_land"], r["harvest_tarp"]),
        ("Sản lượng tiêu thụ (tấn)", t["sold_total"], r["sold_land"], r["sold_tarp"]),
        ("Sản lượng còn lại (tấn)", t["remaining_total"], r["remaining_land"], r["remaining_tarp"]),
        ("Thiệt hại do mưa trái mùa (tấn)", t["damage_total"], r["damage_land"], r["damage_tarp"]),
    ]
    trs = ''.join(f'<tr><td>{esc(a)}</td><td>{fmt_num(b)}</td><td>{fmt_num(c)}</td><td>{fmt_num(d)}</td></tr>' for a,b,c,d in rows)
    logs_html = ''.join(f'<tr><td>{esc(l["created_at"])}</td><td>{esc(l["username"] or "")}</td><td>{esc(l["action"])}</td><td>{esc(l["detail"])}</td></tr>' for l in logs) or '<tr><td colspan="4" class="empty">Chưa có nhật ký.</td></tr>'
    actions = record_action_buttons(session, r)
    body = f"""
    <div class="container">{take_flash(session)}
      <div class="page-head"><div><h1>{esc(r['unit_name'])} · {esc(r['report_date'])}</h1><div class="subtitle"><span class="status {esc(r['status'])}">{STATUS_LABELS[r['status']]}</span></div></div>{actions}</div>
      <div class="card"><div class="table-wrap"><table class="summary-table"><thead><tr><th>Chỉ tiêu</th><th>Cộng</th><th>Muối đất</th><th>Muối trải bạt</th></tr></thead><tbody>{trs}</tbody></table></div>
      <div class="section-title">Chỉ tiêu khác</div><div class="grid">
        <div><b>Muối chế biến:</b> {fmt_num(t['processed_total'])} tấn<br><span class="muted">Muối tinh {fmt_num(r['processed_fine'])}; I-ốt {fmt_num(r['processed_iodized'])}</span></div>
        <div><b>Số hộ:</b> {fmt_num(r['households'])} hộ<br><b>Lao động:</b> {fmt_num(r['workers'])} người</div>
        <div><b>Giá muối đất:</b> {esc(r['price_land'] or '-')}<br><b>Giá trải bạt:</b> {esc(r['price_tarp'] or '-')}</div>
        <div><b>Năng suất BQ:</b> {fmt_num(t['avg_yield'],2)} tấn/ha</div>
      </div>
      <div class="section-title">Ghi chú đơn vị</div><div>{esc(r['note'] or '-')}</div>
      <div class="section-title">Ý kiến Chi cục</div><div>{esc(r['reviewer_note'] or '-')}</div>
      </div>
      <div class="card"><div class="section-title" style="margin-top:0">Nhật ký xử lý</div><div class="table-wrap"><table class="summary-table"><thead><tr><th>Thời gian</th><th>Tài khoản</th><th>Hành động</th><th>Nội dung</th></tr></thead><tbody>{logs_html}</tbody></table></div></div>
    </div>
    """
    return base_page("Chi tiết báo cáo", body, session)


def return_page(session, rid):
    con = db_conn(); r = con.execute("SELECT * FROM records WHERE id=?",(rid,)).fetchone(); con.close()
    if not r or not is_chi_cuc_user(session):
        return None
    body = f"""
    <div class="container"><div class="page-head"><div><h1>Yêu cầu chỉnh sửa</h1><div class="subtitle">{esc(r['unit_name'])} · {esc(r['report_date'])}</div></div></div>
    <form class="card" method="post" action="/records/{rid}/return">{csrf_input(session)}<div class="field"><label>Nội dung yêu cầu đơn vị cập nhật</label><textarea name="reviewer_note" required autofocus>{esc(r['reviewer_note'])}</textarea></div><div class="actions" style="margin-top:12px"><button class="btn warn">Gửi yêu cầu chỉnh sửa</button><a class="btn" href="/records/{rid}">Hủy</a></div></form></div>
    """
    return base_page("Yêu cầu chỉnh sửa", body, session)

def users_page(session):
    if not can_manage_users(session):
        return None

    con = db_conn()
    users = repositories.list_users(con)
    con.close()

    trs = ""
    for u in users:
        cannot_delete = u["id"] == session["user_id"]

        actions = f"""
        <div class="actions">
            <a class="btn small" href="/users/{u['id']}/edit">Sửa</a>
        """

        if not cannot_delete:
            actions += f"""
            <form method="post"
                  action="/users/{u['id']}/{'deactivate' if u['active'] else 'activate'}"
                  style="display:inline"
                  >
                {csrf_input(session)}
                <button class="btn small warn" type="submit">{"Ngưng kích hoạt" if u["active"] else "Kích hoạt lại"}</button>
            </form>
            """

        actions += "</div>"

        trs += f"""
        <tr>
            <td>{esc(u["username"])}</td>
            <td>{esc(ROLE_LABELS.get(u["role"], u["role"]))}</td>
            <td>{esc(u["unit_name"] or "")}</td>
            <td>{"Hoạt động" if u["active"] else "Ngưng hoạt động"}</td>
            <td>{actions}</td>
        </tr>
        """

    body = f"""
    <div class="container">
      {take_flash(session)}

      <div class="page-head">
        <div>
          <h1>Tài khoản đơn vị</h1>
          <div class="subtitle">
            Quản lý tài khoản Chi cục và các đơn vị xã/phường.
          </div>
        </div>
        {'<a class="btn" href="/ocop/access">Phân địa bàn OCOP</a>' if ocop_available() else ''}
      </div>

      <div class="card">
        <form method="post" action="/users/new">
          {csrf_input(session)}
          <div class="grid">

            <div class="field">
              <label>Tên đăng nhập</label>
              <input name="username" required>
            </div>

            <div class="field">
              <label>Mật khẩu ban đầu</label>
              <input type="password" name="password" required minlength="6">
            </div>

            <div class="field">
              <label>Vai trò</label>
              <select name="role">
                <option value="unit">Đơn vị xã/phường</option>
                <option value="staff">Chuyên viên Chi cục</option>
                <option value="admin">Quản trị Chi cục</option>
              </select>
            </div>

            <div class="field">
              <label>Tên đơn vị</label>
              <input name="unit_name" required placeholder="Xã/Phường...">
            </div>

          </div>

          <button class="btn primary" style="margin-top:12px">
            + Thêm tài khoản
          </button>
        </form>
      </div>

      <div class="card">
        <div class="table-wrap">
          <table class="summary-table">
            <thead>
              <tr>
                <th>Tên đăng nhập</th>
                <th>Vai trò</th>
                <th>Đơn vị</th>
                <th>Trạng thái</th>
                <th>Thao tác</th>
              </tr>
            </thead>
            <tbody>
              {trs}
            </tbody>
          </table>
        </div>
      </div>

    </div>
    """

    return base_page("Tài khoản", body, session)


def user_edit_page(session, user, error=""):
    if not can_manage_users(session):
        return None

    notice = (
        f'<div class="notice err">{esc(error)}</div>'
        if error else ""
    )

    unit_selected = "selected" if user["role"] == ROLE_UNIT else ""
    staff_selected = "selected" if user["role"] == ROLE_STAFF else ""
    admin_selected = "selected" if user["role"] == ROLE_ADMIN else ""
    active_checked = "checked" if user["active"] else ""

    body = f"""
    <div class="container">

      <div class="page-head">
        <div>
          <h1>Sửa tài khoản</h1>
          <div class="subtitle">
            Cập nhật thông tin tài khoản và đơn vị.
          </div>
        </div>

        <a class="btn" href="/users">← Quay lại</a>
      </div>

      {notice}

      <form class="card"
            method="post"
            action="/users/{user['id']}/edit">

        {csrf_input(session)}

        <div class="grid">

          <div class="field">
            <label>Tên đăng nhập</label>
            <input name="username"
                   value="{esc(user['username'])}"
                   required>
          </div>

          <div class="field">
            <label>Mật khẩu mới</label>
            <input type="password"
                   name="password"
                   minlength="6"
                   placeholder="Để trống nếu không đổi">
          </div>

          <div class="field">
            <label>Vai trò</label>
            <select name="role">
              <option value="unit" {unit_selected}>
                Đơn vị xã/phường
              </option>

              <option value="staff" {staff_selected}>Chuyên viên Chi cục</option>
              <option value="admin" {admin_selected}>
                Quản trị Chi cục
              </option>
            </select>
          </div>

          <div class="field">
            <label>Tên đơn vị</label>
            <input name="unit_name"
                   value="{esc(user['unit_name'] or '')}"
                   required>
          </div>

          <div class="field">
            <label>
              <input type="checkbox"
                     name="active"
                     value="1"
                     {active_checked}>
              Cho phép đăng nhập
            </label>
          </div>

        </div>

        <div class="actions" style="margin-top:16px">
          <button class="btn primary" type="submit">
            Lưu thay đổi
          </button>

          <a class="btn" href="/users">Hủy</a>
        </div>

      </form>

    </div>
    """

    return base_page("Sửa tài khoản", body, session)

def legacy_import_excel_page(session):
    if not is_chi_cuc_user(session):
        return None

    body = f"""
    <div class="container">

        {take_flash(session)}

        <div class="page-head">
            <div>
                <h1>Import dữ liệu Excel</h1>

                <div class="subtitle">
                    Nhập dữ liệu sản xuất muối từ file Excel lịch sử.
                </div>
            </div>

            <a class="btn" href="/records">
                ← Dữ liệu báo cáo
            </a>
        </div>

        <form
            class="card"
            method="post"
            action="/import-excel"
            enctype="multipart/form-data"
        >

            {csrf_input(session)}

            <div class="grid">

                <div class="field">
                    <label>File Excel (.xlsx)</label>

                    <input
                        type="file"
                        name="excel_file"
                        accept=".xlsx"
                        required
                    >
                </div>


                <div class="field">
                    <label>Ngày/kỳ báo cáo</label>

                    <input
                        type="date"
                        name="report_date"
                        required
                    >
                </div>


                <div class="field">
                    <label>Tên sheet</label>

                    <input
                        name="sheet_name"
                        placeholder="Ví dụ: 03-02. Để trống = sheet đầu tiên"
                    >
                </div>


                <div class="field">
                    <label>Nếu dữ liệu đã tồn tại</label>

                    <select name="mode">

                        <option value="skip">
                            Bỏ qua dữ liệu đã có
                        </option>

                        <option value="update">
                            Cập nhật lại dữ liệu
                        </option>

                    </select>
                </div>

            </div>


            <div class="notice info" style="margin-top:16px">

                Hệ thống sẽ đọc các xã/phường trong cột B và tự bỏ qua
                dòng TỔNG CỘNG.

                <br><br>

                Các cột Cộng và Năng suất bình quân không cần import
                vì hệ thống tự tính.

            </div>


            <button
                class="btn primary"
                type="submit"
                style="margin-top:16px"
            >
                Import vào database
            </button>

        </form>

    </div>
    """

    return base_page(
        "Import Excel",
        body,
        session
    )

def legacy_import_excel_data(
    session,
    file_bytes,
    report_date,
    sheet_name="",
    mode="skip",
    filename=""
):
    if not is_chi_cuc_user(session):
        return False, "Không có quyền import dữ liệu."

    try:
        date.fromisoformat(report_date)
    except ValueError:
        return False, "Ngày báo cáo không hợp lệ."

    try:
        from openpyxl import load_workbook
    except Exception:
        return False, "Chưa cài openpyxl."

    try:
        wb = load_workbook(
            io.BytesIO(file_bytes),
            data_only=True
        )
    except Exception as e:
        return False, f"Không đọc được file Excel: {e}"


    if sheet_name:

        if sheet_name not in wb.sheetnames:
            return False, (
                f"Không tìm thấy sheet '{sheet_name}'. "
                f"Các sheet hiện có: {', '.join(wb.sheetnames)}"
            )

        ws = wb[sheet_name]

    else:
        ws = wb.active


    con = db_conn()

    inserted = 0
    updated = 0
    skipped = 0

    try:

        for row in range(1, ws.max_row + 1):

            # Cột B = tên xã/phường
            unit_name = excel_text(
                ws.cell(row=row, column=2).value
            )

            if not unit_name:
                continue


            unit_check = unit_name.casefold()


            # Bỏ dòng tổng cộng
            if "tổng cộng" in unit_check:
                continue


            # Chỉ lấy dòng đơn vị
            if not unit_check.startswith(
                (
                    "xã ",
                    "phường ",
                    "thị trấn "
                )
            ):
                continue

            official_unit = canonical_admin_unit(unit_name)
            if not official_unit:
                raise ValueError(f"Đơn vị chưa có trong danh mục chính thức: {unit_name}")
            unit_name, unit_code = official_unit


            record = {

                "report_date": report_date,

                "unit_name": unit_name,

                "created_by": session["user_id"],


                # D, E
                "area_land":
                    fnum(ws.cell(row=row, column=4).value),

                "area_tarp":
                    fnum(ws.cell(row=row, column=5).value),


                # G, H
                "harvest_land":
                    fnum(ws.cell(row=row, column=7).value),

                "harvest_tarp":
                    fnum(ws.cell(row=row, column=8).value),


                # J, K
                "sold_land":
                    fnum(ws.cell(row=row, column=10).value),

                "sold_tarp":
                    fnum(ws.cell(row=row, column=11).value),


                # M, N
                "remaining_land":
                    fnum(ws.cell(row=row, column=13).value),

                "remaining_tarp":
                    fnum(ws.cell(row=row, column=14).value),


                # P, Q
                "processed_fine":
                    fnum(ws.cell(row=row, column=16).value),

                "processed_iodized":
                    fnum(ws.cell(row=row, column=17).value),


                # R, S
                "households":
                    fint(ws.cell(row=row, column=18).value),

                "workers":
                    fint(ws.cell(row=row, column=19).value),


                # T, U
                "price_land":
                    excel_text(
                        ws.cell(row=row, column=20).value
                    ),

                "price_tarp":
                    excel_text(
                        ws.cell(row=row, column=21).value
                    ),


                # X, Y
                "damage_land":
                    fnum(ws.cell(row=row, column=24).value),

                "damage_tarp":
                    fnum(ws.cell(row=row, column=25).value),


                "status": STATUS_APPROVED,

                "note":
                    f"Import Excel: {filename} / {ws.title}",

                "created_at": now_text(),

                "updated_at": now_text(),

                "submitted_at": now_text(),

                "approved_at": now_text()
            }


            existing = con.execute(
                """
                SELECT id
                FROM records
                WHERE unit_name=?
                  AND report_date=?
                """,
                (
                    unit_name,
                    report_date
                )
            ).fetchone()


            # =====================
            # ĐÃ CÓ DỮ LIỆU
            # =====================
            if existing:

                if mode != "update":
                    existing_record = con.execute(
                        "SELECT * FROM records WHERE id=?",
                        (existing["id"],),
                    ).fetchone()
                    if existing_record and existing_record["status"] == STATUS_APPROVED:
                        sync_standard_salt_record(con, existing_record)
                    skipped += 1
                    continue


                record["id"] = existing["id"]


                con.execute(
                    """
                    UPDATE records
                    SET
                        area_land=:area_land,
                        area_tarp=:area_tarp,

                        harvest_land=:harvest_land,
                        harvest_tarp=:harvest_tarp,

                        sold_land=:sold_land,
                        sold_tarp=:sold_tarp,

                        remaining_land=:remaining_land,
                        remaining_tarp=:remaining_tarp,

                        processed_fine=:processed_fine,
                        processed_iodized=:processed_iodized,

                        households=:households,
                        workers=:workers,

                        price_land=:price_land,
                        price_tarp=:price_tarp,

                        damage_land=:damage_land,
                        damage_tarp=:damage_tarp,

                        status=:status,

                        updated_at=:updated_at,
                        approved_at=:approved_at

                    WHERE id=:id
                    """,
                    record
                )
                con.execute(
                    "UPDATE records SET reporting_mode='cumulative',ma_don_vi_hanh_chinh=? WHERE id=?",
                    (unit_code, existing["id"]),
                )


                add_audit(
                    con,
                    existing["id"],
                    session["user_id"],
                    "Import Excel",
                    f"Cập nhật dữ liệu từ {filename} / {ws.title}"
                )

                updated_record = con.execute(
                    "SELECT * FROM records WHERE id=?",
                    (existing["id"],),
                ).fetchone()
                sync_standard_salt_record(con, updated_record)

                updated += 1


            # =====================
            # DỮ LIỆU MỚI
            # =====================
            else:

                cur = con.execute(
                    """
                    INSERT INTO records
                    (
                        report_date,
                        unit_name,
                        created_by,

                        area_land,
                        area_tarp,

                        harvest_land,
                        harvest_tarp,

                        sold_land,
                        sold_tarp,

                        remaining_land,
                        remaining_tarp,

                        processed_fine,
                        processed_iodized,

                        households,
                        workers,

                        price_land,
                        price_tarp,

                        damage_land,
                        damage_tarp,

                        status,
                        note,

                        created_at,
                        updated_at,

                        submitted_at,
                        approved_at
                    )

                    VALUES
                    (
                        :report_date,
                        :unit_name,
                        :created_by,

                        :area_land,
                        :area_tarp,

                        :harvest_land,
                        :harvest_tarp,

                        :sold_land,
                        :sold_tarp,

                        :remaining_land,
                        :remaining_tarp,

                        :processed_fine,
                        :processed_iodized,

                        :households,
                        :workers,

                        :price_land,
                        :price_tarp,

                        :damage_land,
                        :damage_tarp,

                        :status,
                        :note,

                        :created_at,
                        :updated_at,

                        :submitted_at,
                        :approved_at
                    )
                    """,
                    record
                )
                con.execute(
                    "UPDATE records SET reporting_mode='cumulative',ma_don_vi_hanh_chinh=? WHERE id=?",
                    (unit_code, cur.lastrowid),
                )


                add_audit(
                    con,
                    cur.lastrowid,
                    session["user_id"],
                    "Import Excel",
                    f"Import từ {filename} / {ws.title}"
                )

                inserted_record = con.execute(
                    "SELECT * FROM records WHERE id=?",
                    (cur.lastrowid,),
                ).fetchone()
                sync_standard_salt_record(con, inserted_record)

                inserted += 1


        con.commit()


    except Exception as e:

        con.rollback()
        con.close()

        return False, f"Lỗi khi import: {e}"


    con.close()


    return True, (
        f"Import hoàn tất. "
        f"Thêm mới: {inserted}; "
        f"Cập nhật: {updated}; "
        f"Bỏ qua: {skipped}."
    )

def import_excel_page(session):
    if not is_chi_cuc_user(session):
        return None
    con = db_conn()
    batches = con.execute(
        """SELECT b.*,u.username FROM salt_import_batches b
           JOIN users u ON u.id=b.imported_by ORDER BY b.id DESC LIMIT 8"""
    ).fetchall()
    con.close()
    history = ''.join(
        f"<tr><td>{esc(b['week_code'])}</td><td>{esc(b['filename'])}</td>"
        f"<td>{esc(b['sheet_name'])}</td><td>{b['imported_rows']}</td>"
        f"<td>{b['updated_rows']}</td><td>{b['skipped_rows']}</td><td>{esc(b['username'])}</td></tr>"
        for b in batches
    ) or '<tr><td colspan="7" class="empty">Chưa có đợt import tuần.</td></tr>'
    body = f"""
    <div class="container weekly-page">
      {take_flash(session)}
      <div class="page-head"><div><h1>Import báo cáo tuần</h1>
        <div class="subtitle">Bước 1: chọn file. Hệ thống chỉ xem trước và kiểm tra, chưa ghi database.</div></div>
        <a class="btn" href="/salt/weekly">Tra cứu tuần</a></div>
      {salt_data_tabs(session, "/import-excel")}
      <form class="card import-card js-loading-form" method="post" action="/import-excel" enctype="multipart/form-data">
        {csrf_input(session)}
        <div class="weekly-step"><span>1</span><div><strong>Chọn dữ liệu tuần</strong><small>File được kiểm tra trước khi import.</small></div></div>
        <div class="grid">
          <div class="field"><label>File Excel (.xlsx)</label><input type="file" name="excel_file" accept=".xlsx" required></div>
          <div class="field"><label>Ngày chốt số liệu tuần</label><input type="date" name="report_date" required></div>
          <div class="field"><label>Tên sheet</label><input name="sheet_name" placeholder="Ví dụ: 21.8-Tuan 34"></div>
        </div>
        <div class="notice info">Cột B phải là xã/phường chính thức. C/F là tổng diện tích và sản lượng; D/E, G/H là chi tiết nền đất và nền trải bạt.</div>
        <button class="btn primary" type="submit" data-loading-text="Đang đọc và kiểm tra Excel...">Kiểm tra và xem trước</button>
      </form>
      <section class="card"><h2 class="section-title">Lịch sử import gần đây</h2>
        <div class="table-wrap"><table class="summary-table"><thead><tr><th>Tuần</th><th>File</th><th>Sheet</th><th>Mới</th><th>Cập nhật</th><th>Bỏ qua</th><th>Người import</th></tr></thead><tbody>{history}</tbody></table></div>
      </section>
    </div>"""
    return base_page("Import báo cáo tuần", body, session, active_path="/import-excel")


def import_preview_page(session):
    if not is_chi_cuc_user(session):
        return None
    preview = session.get("weekly_import_preview")
    if not preview:
        set_flash(session, "err", "Chưa có dữ liệu xem trước. Hãy chọn file Excel.")
        return None
    rows_html = []
    for row in preview["rows"]:
        data = row["canonical"]
        messages = row["errors"] + row["warnings"]
        label = {"valid":"Hợp lệ", "warning":"Cảnh báo", "error":"Lỗi"}[row["status"]]
        rows_html.append(
            f'<tr class="preview-{row["status"]}"><td>{row["excel_row"]}</td>'
            f'<td><strong>{esc(data["unit_name"])}</strong><small>{esc(data.get("ma_don_vi_hanh_chinh") or "Chưa có mã")}</small></td>'
            f'<td>{fmt_num(data["dien_tich"],2)}</td><td>{fmt_num(data["san_luong"],2)}</td>'
            f'<td><span class="validation-badge {row["status"]}">{label}</span>'
            f'<div class="validation-message">{esc("; ".join(messages))}</div></td></tr>'
        )
    blocked = preview["error_rows"] > 0
    confirm = f"""
      <form class="confirm-import" method="post" action="/import-excel/confirm">
        {csrf_input(session)}
        <div class="field"><label>Nếu xã/tuần đã tồn tại</label><select name="mode"><option value="skip">Giữ dữ liệu hiện tại</option><option value="update">Cập nhật bằng file này</option></select></div>
        <button class="btn primary" type="submit" {'disabled' if blocked else ''}>Xác nhận import</button>
      </form>""" if not blocked else '<div class="notice err">Cần sửa các dòng lỗi trong Excel rồi tải lại file.</div>'
    body = f"""
    <div class="container weekly-page">
      {take_flash(session)}
      <div class="page-head"><div><h1>Xem trước báo cáo tuần</h1>
        <div class="subtitle">Bước 2: kiểm tra {esc(preview['filename'])} · {esc(preview['sheet_name'])} · {esc(preview['week_code'])}</div></div>
        <a class="btn" href="/import-excel">Chọn file khác</a></div>
      {salt_data_tabs(session, "/import-excel")}
      <div class="validation-summary">
        <div><strong>{len(preview['rows'])}</strong><span>Tổng số xã</span></div>
        <div class="valid"><strong>{preview['valid_rows']}</strong><span>Hợp lệ</span></div>
        <div class="warning"><strong>{preview['warning_rows']}</strong><span>Cảnh báo</span></div>
        <div class="error"><strong>{preview['error_rows']}</strong><span>Lỗi</span></div>
      </div>
      <section class="card"><div class="table-wrap"><table class="summary-table preview-table"><thead><tr><th>Dòng Excel</th><th>Đơn vị</th><th>Diện tích (ha)</th><th>Sản lượng (tấn)</th><th>Kết quả</th></tr></thead><tbody>{''.join(rows_html)}</tbody></table></div></section>
      {confirm}
    </div>"""
    return base_page("Xem trước import tuần", body, session, active_path="/import-excel")


def _weekly_excel_value(value):
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return fmt_num(value, 2)
    token = str(value)
    try:
        parsed = datetime.fromisoformat(token)
        return parsed.strftime("%d/%m/%Y")
    except ValueError:
        return token


def _weekly_total(raw_rows, column):
    values = []
    for raw in raw_rows:
        value = raw.get(str(column), {}).get("value")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            values.append(float(value))
    if column in (20, 21):
        non_zero = [value for value in values if value]
        return sum(non_zero) / len(non_zero) if non_zero else None
    return sum(values)


def weekly_records_page(session, query):
    """Browse one imported workbook sheet as one report."""
    params = parse_qs(query)
    con = db_conn()
    batches = con.execute(
        """SELECT b.*,u.username FROM salt_import_batches b
           JOIN users u ON u.id=b.imported_by
           ORDER BY b.report_date DESC,b.id DESC"""
    ).fetchall()
    requested_batch = params.get("batch", [""])[0].strip()
    selected = next((batch for batch in batches if str(batch["id"]) == requested_batch), None)
    if not selected:
        requested_week = params.get("week", [""])[0].strip()
        selected = next((batch for batch in batches if batch["week_code"] == requested_week), None)
    if not selected and batches:
        selected = batches[0]

    rows = []
    if selected:
        sql = """SELECT excel_row,unit_name_raw,ma_don_vi_hanh_chinh,
                        validation_status,validation_messages_json,raw_data_json
                 FROM salt_weekly_import_rows WHERE batch_id=?"""
        args = [selected["id"]]
        if session["role"] == ROLE_UNIT:
            official = canonical_admin_unit(session["unit_name"])
            sql += " AND ma_don_vi_hanh_chinh=?"
            args.append(official[1] if official else "")
        sql += " ORDER BY excel_row"
        rows = con.execute(sql, args).fetchall()
    con.close()

    options = ''.join(
        f'<option value="{batch["id"]}" {"selected" if selected and batch["id"] == selected["id"] else ""}>'
        f'{esc(batch["sheet_name"])} · {esc(batch["week_code"])} · {esc(batch["filename"])}</option>'
        for batch in batches
    )
    if not selected:
        report = '<section class="card empty">Chưa có sheet báo cáo tuần nào được import.</section>'
    else:
        raw_rows = [json.loads(row["raw_data_json"]) for row in rows]
        detail_rows = []
        for raw in raw_rows:
            cells = ''.join(f'<td>{esc(_weekly_excel_value(raw.get(str(column), {}).get("value")))}</td>' for column in range(1, 29))
            detail_rows.append(f'<tr>{cells}</tr>')
        total_cells = ['<th></th>', '<th>TỔNG CỘNG</th>']
        for column in range(3, 29):
            if column == 22:
                area, production = _weekly_total(raw_rows, 3), _weekly_total(raw_rows, 6)
                value = production / area if area else None
            elif column in tuple(range(3, 22)) + tuple(range(23, 27)):
                value = _weekly_total(raw_rows, column)
            else:
                value = None
            total_cells.append(f'<th>{esc(_weekly_excel_value(value))}</th>')
        report_date = selected["report_date"]
        try:
            report_date = date.fromisoformat(str(report_date)).strftime("%d/%m/%Y")
        except ValueError:
            report_date = str(report_date)
        report = f"""
        <section class="sheet-report">
          <div class="sheet-meta">
            <div><span>Sheet báo cáo</span><strong>{esc(selected['sheet_name'])}</strong></div>
            <div><span>Ngày chốt</span><strong>{esc(report_date)}</strong></div>
            <div><span>Tuần</span><strong>{esc(selected['week_code'])}</strong></div>
            <div><span>Số dòng đơn vị</span><strong>{len(rows)}</strong></div>
          </div>
          <div class="excel-sheet-wrap"><table class="excel-sheet">
            <caption>Báo cáo tình hình sản xuất, chế biến, tiêu thụ niên vụ muối — lũy tiến đến ngày {esc(report_date)}</caption>
            <thead>
              <tr><th rowspan="2">TT</th><th rowspan="2">Thành phố/huyện/thị xã</th><th colspan="3">Diện tích sản xuất muối (ha)</th><th colspan="3">Sản lượng muối thu hoạch (tấn)</th><th colspan="3">Sản lượng muối tiêu thụ (tấn)</th><th colspan="3">Sản lượng còn lại (tấn)</th><th colspan="3">Sản lượng muối chế biến (tấn)</th><th rowspan="2">Số hộ làm muối</th><th rowspan="2">Số lao động</th><th colspan="2">Giá bán (đồng/kg)</th><th rowspan="2">Năng suất BQ</th><th colspan="3">Thiệt hại do mưa trái mùa</th><th rowspan="2">Diện tích mất trắng</th><th rowspan="2">Ghi chú</th><th rowspan="2">Thời gian kết thúc niên vụ</th></tr>
              <tr><th>Cộng</th><th>Muối đất</th><th>Muối trải bạt</th><th>Cộng</th><th>Muối đất</th><th>Muối trải bạt</th><th>Cộng</th><th>Muối đất</th><th>Muối trải bạt</th><th>Cộng</th><th>Muối đất</th><th>Muối trải bạt</th><th>Cộng</th><th>Muối tinh</th><th>Muối I-ốt</th><th>Muối đất</th><th>Muối trải bạt</th><th>Cộng</th><th>Muối đất</th><th>Muối trải bạt</th></tr>
            </thead>
            <tbody><tr class="sheet-total">{''.join(total_cells)}</tr>{''.join(detail_rows)}</tbody>
          </table></div>
          <p class="sheet-footnote">Nguồn: {esc(selected['filename'])} · Import bởi {esc(selected['username'])} lúc {esc(selected['imported_at'])}. Mỗi sheet là một báo cáo; mỗi xã/phường là một dòng trong báo cáo.</p>
        </section>"""

    body = f"""
    <div class="container weekly-page">
      {take_flash(session)}
      <div class="page-head"><div><h1>Tra cứu sheet báo cáo tuần</h1><div class="subtitle">Chọn một sheet đã import để đọc lại toàn bộ bảng theo bố cục Excel.</div></div>
        {'<a class="btn primary" href="/import-excel">Import Excel</a>' if is_chi_cuc_user(session) else ''}</div>
      {salt_data_tabs(session, "/salt/weekly")}
      <form class="card weekly-filter" method="get"><div class="field sheet-picker"><label>Sheet đã import</label><select name="batch">{options}</select></div><button class="btn primary">Mở bảng</button><div class="weekly-progress"><strong>{len(batches)}</strong><span>sheet báo cáo</span></div></form>
      {report}
    </div>"""
    return base_page("Tra cứu báo cáo tuần", body, session, active_path="/salt/weekly")


def change_password_page(session, error=""):
    notice = f'<div class="notice err">{esc(error)}</div>' if error else ''
    body = f"""<div class="container"><div class="page-head"><div><h1>Đổi mật khẩu</h1></div></div>{notice}<form class="card" method="post" action="/change-password">{csrf_input(session)}<div class="grid"><div class="field"><label>Mật khẩu hiện tại</label><input type="password" name="old" required></div><div class="field"><label>Mật khẩu mới</label><input type="password" name="new" minlength="8" required></div><div class="field"><label>Nhập lại mật khẩu mới</label><input type="password" name="new2" minlength="8" required></div></div><button class="btn primary" style="margin-top:12px">Đổi mật khẩu</button></form></div>"""
    return base_page("Đổi mật khẩu", body, session)


def save_record(session, data, rid=None):
    unit_name = session["unit_name"] if session["role"] == ROLE_UNIT else data.get("unit_name", "").strip()
    report_date = data.get("report_date", "").strip()
    if not unit_name or not report_date:
        return False, "Vui lòng chọn đơn vị và ngày/kỳ chốt số liệu."
    official_unit = canonical_admin_unit(unit_name)
    if not official_unit:
        return False, f"Đơn vị {unit_name} chưa có trong danh mục hành chính chính thức."
    unit_code = official_unit[1] if official_unit else None
    unit_name = official_unit[0] if official_unit else unit_name
    try:
        date.fromisoformat(report_date)
    except ValueError:
        return False, "Ngày báo cáo không hợp lệ."
    values = {k: fnum(data.get(k,0)) for k in NUMERIC_FIELDS}
    values["households"] = fint(data.get("households",0))
    values["workers"] = fint(data.get("workers",0))
    price_land = data.get("price_land", "").strip()
    price_tarp = data.get("price_tarp", "").strip()
    note = data.get("note", "").strip()
    con = db_conn()
    try:
        if rid is None:
            cur = con.execute(
                """INSERT INTO records(report_date,unit_name,created_by,area_land,area_tarp,harvest_land,harvest_tarp,sold_land,sold_tarp,remaining_land,remaining_tarp,processed_fine,processed_iodized,households,workers,price_land,price_tarp,damage_land,damage_tarp,status,note,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'draft',?,?,?)""",
                (report_date, unit_name, session["user_id"], values["area_land"], values["area_tarp"], values["harvest_land"], values["harvest_tarp"], values["sold_land"], values["sold_tarp"], values["remaining_land"], values["remaining_tarp"], values["processed_fine"], values["processed_iodized"], values["households"], values["workers"], price_land, price_tarp, values["damage_land"], values["damage_tarp"], note, now_text(), now_text())
            )
            rid = cur.lastrowid
            con.execute(
                "UPDATE records SET reporting_mode='cumulative',ma_don_vi_hanh_chinh=? WHERE id=?",
                (unit_code, rid),
            )
            add_audit(con, rid, session["user_id"], "Tạo báo cáo", "Lưu bản nháp")
        else:
            r = con.execute("SELECT * FROM records WHERE id=?", (rid,)).fetchone()
            if not r or not can_access_record(session, r):
                return False, "Không có quyền sửa báo cáo này."
            if session["role"] == ROLE_UNIT and r["status"] not in (STATUS_DRAFT, STATUS_RETURNED):
                return False, "Báo cáo đã gửi/duyệt nên đơn vị không thể sửa."
            con.execute(
                """UPDATE records SET report_date=?,unit_name=?,area_land=?,area_tarp=?,harvest_land=?,harvest_tarp=?,sold_land=?,sold_tarp=?,remaining_land=?,remaining_tarp=?,processed_fine=?,processed_iodized=?,households=?,workers=?,price_land=?,price_tarp=?,damage_land=?,damage_tarp=?,note=?,updated_at=? WHERE id=?""",
                (report_date, unit_name, values["area_land"], values["area_tarp"], values["harvest_land"], values["harvest_tarp"], values["sold_land"], values["sold_tarp"], values["remaining_land"], values["remaining_tarp"], values["processed_fine"], values["processed_iodized"], values["households"], values["workers"], price_land, price_tarp, values["damage_land"], values["damage_tarp"], note, now_text(), rid)
            )
            con.execute(
                "UPDATE records SET reporting_mode='cumulative',ma_don_vi_hanh_chinh=? WHERE id=?",
                (unit_code, rid),
            )
            add_audit(con, rid, session["user_id"], "Cập nhật báo cáo", "Chỉnh sửa số liệu")
        con.commit()
        return True, rid
    except INTEGRITY_ERRORS:
        con.rollback()
        return False, f"Đơn vị {unit_name} đã có báo cáo ngày {report_date}. Hãy mở báo cáo đó để cập nhật."
    finally:
        con.close()


def export_xlsx(session, filters):
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
        from openpyxl.utils import get_column_letter
    except Exception:
        return None, None
    con = db_conn(); records = fetch_records(con, session, filters); con.close()
    wb = Workbook(); ws = wb.active; ws.title = "Tong hop"
    headers1 = ["TT", "Đơn vị", "Diện tích sản xuất muối (ha)", "", "", "Sản lượng muối thu hoạch (tấn)", "", "", "Sản lượng muối tiêu thụ (tấn)", "", "", "Sản lượng còn lại (tấn)", "", "", "Sản lượng muối chế biến (tấn)", "", "", "Số hộ làm muối (hộ)", "Số lao động làm muối (người)", "Giá bán (đồng/kg)", "", "Năng suất BQ (tấn/ha)", "Thiệt hại do mưa trái mùa (tấn)", "", "", "Kỳ báo cáo", "Trạng thái"]
    headers2 = ["", "", "Cộng", "Muối đất", "Muối trải bạt", "Cộng", "Muối đất", "Muối trải bạt", "Cộng", "Muối đất", "Muối trải bạt", "Cộng", "Muối đất", "Muối trải bạt", "Cộng", "Muối tinh", "Muối I-ốt", "", "", "Muối đất", "Muối trải bạt", "", "Cộng", "Muối đất", "Muối trải bạt", "", ""]
    ws.append(headers1); ws.append(headers2)
    merges = [(1,3,1,5),(1,6,1,8),(1,9,1,11),(1,12,1,14),(1,15,1,17),(1,20,1,21),(1,23,1,25)]
    for a,b,c,d in merges: ws.merge_cells(start_row=a,start_column=b,end_row=c,end_column=d)
    for col in [1,2,18,19,22,26,27]: ws.merge_cells(start_row=1,start_column=col,end_row=2,end_column=col)
    thin = Side(style="thin", color="B8C2CC")
    for row in ws.iter_rows(min_row=1,max_row=2,min_col=1,max_col=27):
        for cell in row:
            cell.font = Font(bold=True); cell.alignment = Alignment(horizontal="center",vertical="center",wrap_text=True); cell.fill = PatternFill("solid", fgColor="D9EAF7"); cell.border=Border(left=thin,right=thin,top=thin,bottom=thin)
    sums = [0.0]*23
    for i,r in enumerate(records, start=1):
        t = record_totals(r)
        row = [i,r["unit_name"],t["area_total"],r["area_land"],r["area_tarp"],t["harvest_total"],r["harvest_land"],r["harvest_tarp"],t["sold_total"],r["sold_land"],r["sold_tarp"],t["remaining_total"],r["remaining_land"],r["remaining_tarp"],t["processed_total"],r["processed_fine"],r["processed_iodized"],r["households"],r["workers"],r["price_land"],r["price_tarp"],t["avg_yield"],t["damage_total"],r["damage_land"],r["damage_tarp"],r["report_date"],STATUS_LABELS[r["status"]]]
        ws.append(row)
    ws.freeze_panes = "C3"; ws.auto_filter.ref = f"A2:AA{max(2,ws.max_row)}"
    widths = {1:6,2:25,18:15,19:16,20:18,21:20,22:16,26:13,27:18}
    for c in range(1,28): ws.column_dimensions[get_column_letter(c)].width = widths.get(c,14)
    for row in ws.iter_rows(min_row=3):
        for cell in row: cell.border=Border(left=thin,right=thin,top=thin,bottom=thin)
    bio=io.BytesIO(); wb.save(bio); return bio.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def ocop_access_page(con, session):
    import ocop_services as svc
    if svc.get_scope(con, session) is not None:
        raise svc.OcopError("Chỉ Chi cục được phân địa bàn OCOP.", 403)
    rows = con.execute("""SELECT u.id,u.username,u.unit_name,d.TenDonVi,d.Ma_DonViHanhChinh
        FROM users u LEFT JOIN user_admin_units m ON m.user_id=u.id
        LEFT JOIN DM_DonViHanhChinh d ON d.Ma_DonViHanhChinh=m.ma_don_vi_hanh_chinh
        WHERE u.role='unit' AND u.active=1 ORDER BY u.unit_name,u.username""").fetchall()
    units = svc.unit_options(con, session)
    forms = []
    for row in rows:
        options = '<option value="">Chọn địa bàn chính thức</option>'
        for unit in units:
            selected = ' selected' if unit['code'] == row['Ma_DonViHanhChinh'] else ''
            options += f'<option value="{esc(unit["code"])}"{selected}>{esc(unit["name"])} ({esc(unit["code"])})</option>'
        forms.append(f'''<tr><td>{esc(row['username'])}</td><td>{esc(row['unit_name'])}</td>
          <td><form method="post" action="/ocop/access" class="actions">{csrf_input(session)}
          <input type="hidden" name="user_id" value="{row['id']}">
          <label class="field">Địa bàn OCOP<select name="unit_code" required>{options}</select></label>
          <button class="btn primary" type="submit">Lưu địa bàn</button></form></td></tr>''')
    return "Phân địa bàn OCOP", f'''<div class="container ocop-page">{take_flash(session)}
      <div class="page-head"><h1>Phân địa bàn OCOP</h1><a class="btn" href="/users">Tài khoản</a></div>
      <div class="notice info">Quyền OCOP dùng mã hành chính. Tài khoản chưa được gán địa bàn chưa thể truy cập hồ sơ OCOP.
      Việc gán địa bàn này không đổi tên đơn vị hoặc dữ liệu sản xuất muối.</div>
      <div class="card table-wrap"><table class="summary-table"><thead><tr><th>Tài khoản</th><th>Tên đơn vị hiện tại</th>
      <th>Địa bàn được phép quản lý</th></tr></thead><tbody>{''.join(forms)}</tbody></table></div></div>'''


def save_ocop_access(con, session, data):
    import ocop_services as svc
    if not can_manage_users(session):
        raise svc.OcopError("Chỉ Chi cục được phân địa bàn OCOP.", 403)
    try:
        uid = int(data.get("user_id", ""))
    except (ValueError, TypeError):
        raise svc.OcopError("Tài khoản không hợp lệ.")
    code = str(data.get("unit_code", "")).strip()
    with con:
        con.execute("BEGIN")
        current = get_user(con, session["user_id"])
        if not current or not current["active"] or not can_manage_users(dict(current)):
            raise svc.OcopError("Chỉ quản trị được phân địa bàn OCOP.", 403)
        svc.get_scope(con, session)
        user = con.execute("SELECT id FROM users WHERE id=? AND active=1 AND role='unit'", (uid,)).fetchone()
        unit = con.execute("""SELECT Ma_DonViHanhChinh FROM DM_DonViHanhChinh
            WHERE Ma_DonViHanhChinh=? AND TinhTrang=1 AND CapHanhChinh IN ('xa','phuong')
            AND Ma_DonViHanhChinh NOT LIKE 'TMP%'""", (code,)).fetchone()
        if not user or not unit:
            raise svc.OcopError("Chọn tài khoản đang hoạt động và địa bàn chính thức.")
        old = con.execute("SELECT ma_don_vi_hanh_chinh FROM user_admin_units WHERE user_id=?", (uid,)).fetchone()
        con.execute("""INSERT INTO user_admin_units(user_id,ma_don_vi_hanh_chinh) VALUES(?,?)
            ON CONFLICT(user_id) DO UPDATE SET ma_don_vi_hanh_chinh=excluded.ma_don_vi_hanh_chinh""", (uid,code))
        con.execute("""INSERT INTO audit_logs(record_id,user_id,action,detail,created_at,module,object_type,object_id)
            VALUES(NULL,?,?,?,?, 'ocop','user_scope',?)""",
            (session['user_id'], 'Phân địa bàn OCOP', f"{old[0] if old else ''} -> {code}", now_text(), str(uid)))
    invalidate_user_sessions(uid)


class Handler(BaseHTTPRequestHandler):
    server_version = "SaltData/1.0"

    def log_message(self, format, *args):
        sys.stdout.write("%s - - [%s] %s\n" % (self.client_address[0], self.log_date_time_string(), format%args))

    def send_html(self, content, status=200, extra_headers=None):
        data = content.encode("utf-8")
        self.send_response(status); self.send_header("Content-Type","text/html; charset=utf-8"); self.send_header("Content-Length",str(len(data))); self.send_header("X-Frame-Options","DENY"); self.send_header("X-Content-Type-Options","nosniff")
        if extra_headers:
            for k,v in extra_headers: self.send_header(k,v)
        self.end_headers(); self.wfile.write(data)

    def redirect(self, location, headers=None):
        self.send_response(303); self.send_header("Location", location)
        if headers:
            for k,v in headers: self.send_header(k,v)
        self.end_headers()

    def require_session(self):
        sid,s = get_session(self)
        if not s:
            self.redirect("/"); return None, None
        s["user_id"] = int(s["user_id"])
        return sid,s

    def handle_ocop(self, path, query, session, data=None):
        """OCOP dispatch stays separate from the existing salt routes."""
        if not (path == "/ocop" or path.startswith("/ocop/")):
            return False
        import ocop_services as svc
        import ocop_pages
        con = db_conn()
        active = "/".join(path.split("/")[:3]) if path != "/ocop" else path
        if path == "/ocop/access":
            active = "/users"
        helpers = {"esc": esc, "csrf_input": csrf_input, "icon": icon}
        try:
            if not ocop_available(con):
                raise svc.OcopError("Phân hệ OCOP chưa được khởi tạo trên cơ sở dữ liệu này.", 503)
            if path != "/ocop/access":
                svc.get_scope(con, session)
            if data is None:
                page = ocop_access_page(con, session) if path == "/ocop/access" else ocop_pages.render(path, query, session, con, helpers)
                if page is None:
                    raise svc.OcopError("Không tìm thấy trang OCOP.", 404)
                title, body = page
                body = body.replace('<div class="container ocop-page">', '<div class="container ocop-page">' + take_flash(session), 1)
                self.send_html(base_page(title, body, session, active_path=active))
                return True
            if path == "/ocop/access":
                save_ocop_access(con, session, data)
                destination = path
            else:
                parts = path.strip("/").split("/")
                if len(parts) not in (3, 4) or parts[1] not in ("entities", "products", "applications"):
                    raise svc.OcopError("Không tìm thấy thao tác OCOP.", 404)
                section = parts[1]
                singular = {"entities": "entity", "products": "product", "applications": "application"}[section]
                if len(parts) == 3 and parts[2] == "new":
                    result = getattr(svc, f"create_{singular}")(con, session, data)
                    rid = result["id"] if isinstance(result, dict) else result
                    destination = f"/ocop/{section}/{rid}"
                elif len(parts) == 4 and parts[2].isdigit():
                    rid, action = int(parts[2]), parts[3]
                    if action == "edit":
                        getattr(svc, f"update_{singular}")(con, session, rid, data)
                    elif action == "archive" and section in ("entities", "products"):
                        getattr(svc, f"archive_{singular}")(con, session, rid, data)
                    elif section == "applications" and action in ("submit", "start-review", "return", "eligible", "cancel"):
                        svc.application_action(con, session, rid, action, data)
                    else:
                        raise svc.OcopError("Không tìm thấy thao tác OCOP.", 404)
                    destination = f"/ocop/{section}/{rid}"
                else:
                    raise svc.OcopError("Không tìm thấy thao tác OCOP.", 404)
            set_flash(session, "ok", "Đã lưu thay đổi OCOP.")
            self.redirect(destination)
        except svc.OcopError as exc:
            con.rollback()
            status = getattr(exc, "status", 400)
            page = None
            if data is not None and status in (400, 409) and (path.endswith("/new") or path.endswith("/edit")):
                try:
                    page = ocop_pages.render(path, query, session, con, {**helpers, "form_data":data, "error":str(exc)})
                except (svc.OcopError, ValueError):
                    pass
            if page:
                title, body = page
            else:
                title = "Thông báo OCOP"
                body = f'<div class="container"><div class="notice err">{esc(exc)}</div><a class="btn" href="/ocop">Tổng quan OCOP</a></div>'
            self.send_html(base_page(title, body, session, active_path=active), status)
        except Exception:
            con.rollback()
            logging.exception("OCOP request failed")
            self.send_html(base_page("Thông báo OCOP", '<div class="container"><div class="notice err">Không thể xử lý yêu cầu lúc này. Vui lòng thử lại hoặc liên hệ quản trị.</div></div>', session, active_path=active), 500)
        finally:
            con.close()
        return True

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # =========================
        # ASSETS: CSS / JS / ẢNH
        # =========================
        if path in ASSET_FILES:
            filename, content_type = ASSET_FILES[path]

            try:
                with open(
                    os.path.join(BASE_DIR, "assets", filename),
                    "rb"
                ) as asset_file:
                    content = asset_file.read()

            except FileNotFoundError:
                self.send_error(404, "Asset not found")
                return

            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))

            self.send_header(
                "Cache-Control",
                "no-cache"
                if filename != "quoc-huy.png"
                else "public, max-age=86400"
            )

            self.send_header(
                "X-Content-Type-Options",
                "nosniff"
            )

            self.end_headers()
            self.wfile.write(content)
            return


        # =========================
        # KIỂM TRA SESSION
        # =========================
        sid, session = get_session(self)


        # =========================
        # TRANG ĐĂNG NHẬP
        # =========================
        if path == "/":

            if session:
                self.redirect("/dashboard")

            else:
                self.send_html(login_page())

            return


        # =========================
        # ĐĂNG XUẤT
        # =========================
        if path == "/logout":

            if sid:
                with SESSION_LOCK:
                    SESSIONS.pop(sid, None)

            self.redirect(
                "/",
                [
                    (
                        "Set-Cookie",
                        "salt_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"
                    )
                ]
            )

            return


        # =========================
        # YÊU CẦU ĐĂNG NHẬP
        # =========================
        sid, session = self.require_session()

        if not session:
            return


        # =========================
        # DASHBOARD
        # =========================
        if (path == "/users" or path.startswith("/users/") or path.rstrip("/") == "/ocop/access") and not can_manage_users(session):
            self.send_html(base_page("403", '<div class="container"><div class="notice err">Không có quyền quản lý tài khoản.</div></div>', session), 403)
            return
        if self.handle_ocop(path, parsed.query, session):
            return
        if path == "/dashboard":

            self.send_html(
                dashboard_page(session, parsed.query)
            )

            return


        # =========================
        # DANH SÁCH BÁO CÁO
        # =========================
        if path == "/records":

            self.send_html(
                records_page(
                    session,
                    parsed.query
                )
            )

            return

        if path == "/standard-data":
            p = standard_data_page(session)
            self.send_html(
                p if p else base_page(
                    "403",
                    "<div class='container'><div class='notice err'>Không có quyền.</div></div>",
                    session
                ),
                200 if p else 403
            )
            return

        if path == "/salt/weekly":
            self.send_html(weekly_records_page(session, parsed.query))
            return


        # =========================
        # NHẬP SỐ LIỆU
        # =========================
        if path == "/records/new":

            self.send_html(
                record_form_page(session)
            )

            return

        if path == "/import-excel":

            p = import_excel_page(session)

            self.send_html(
                p
                if p
                else base_page(
                    "403",
                    """
                    <div class='container'>
                        <div class='notice err'>
                            Không có quyền.
                        </div>
                    </div>
                    """,
                    session
                ),
                200 if p else 403
            )

            return
        if path == "/import-excel/preview":
            p = import_preview_page(session)
            if p:
                self.send_html(p)
            else:
                self.redirect("/import-excel")
            return
        # =========================
        # TÀI KHOẢN ĐƠN VỊ
        # =========================
        if path == "/users":

            p = users_page(session)

            self.send_html(
                p
                if p
                else base_page(
                    "403",
                    """
                    <div class='container'>
                        <div class='notice err'>
                            Không có quyền.
                        </div>
                    </div>
                    """,
                    session
                ),
                200 if p else 403
            )

            return


        # =========================
        # ĐỔI MẬT KHẨU
        # =========================
        if path == "/change-password":

            self.send_html(
                change_password_page(session)
            )

            return


        # =========================
        # XUẤT EXCEL
        # =========================
        if path == "/export.xlsx":

            filters = filters_from_query(
                parsed.query,
                session
            )

            content, mime = export_xlsx(
                session,
                filters
            )

            if content is None:

                self.send_html(
                    base_page(
                        "Lỗi",
                        """
                        <div class='container'>
                            <div class='notice err'>
                                Máy chủ chưa có openpyxl.
                                Cài bằng: pip install openpyxl
                            </div>
                        </div>
                        """,
                        session
                    ),
                    500
                )

                return


            self.send_response(200)

            self.send_header(
                "Content-Type",
                mime
            )

            self.send_header(
                "Content-Disposition",
                'attachment; filename="tong_hop_so_lieu_muoi.xlsx"'
            )

            self.send_header(
                "Content-Length",
                str(len(content))
            )

            self.end_headers()

            self.wfile.write(content)

            return


        # =========================
        # TÁCH URL
        # =========================
        parts = [
            p
            for p in path.split("/")
            if p
        ]


        # =========================================
        # MỞ TRANG SỬA TÀI KHOẢN
        # URL: /users/9/edit
        # =========================================
        if (
            len(parts) == 3
            and parts[0] == "users"
            and parts[1].isdigit()
            and parts[2] == "edit"
        ):

            # Chỉ Chi cục được sửa tài khoản
            if not can_manage_users(session):

                self.send_html(
                    base_page(
                        "403",
                        """
                        <div class='container'>
                            <div class='notice err'>
                                Không có quyền.
                            </div>
                        </div>
                        """,
                        session
                    ),
                    403
                )

                return


            uid = int(parts[1])


            con = db_conn()

            user = get_user(con, uid)

            con.close()


            if not user:

                self.send_html(
                    base_page(
                        "404",
                        """
                        <div class='container'>
                            <div class='notice err'>
                                Không tìm thấy tài khoản.
                            </div>
                        </div>
                        """,
                        session
                    ),
                    404
                )

                return


            self.send_html(
                user_edit_page(
                    session,
                    user
                )
            )

            return


        # =========================================
        # CHI TIẾT / SỬA BÁO CÁO
        # =========================================
        if (
            len(parts) >= 2
            and parts[0] == "records"
            and parts[1].isdigit()
        ):

            rid = int(parts[1])


            # =========================
            # XEM CHI TIẾT BÁO CÁO
            # /records/1
            # =========================
            if len(parts) == 2:

                p = detail_page(
                    session,
                    rid
                )

                self.send_html(
                    p
                    if p
                    else base_page(
                        "404",
                        """
                        <div class='container'>
                            <div class='notice err'>
                                Không tìm thấy hoặc không có quyền.
                            </div>
                        </div>
                        """,
                        session
                    ),
                    200 if p else 404
                )

                return


            # =========================
            # SỬA BÁO CÁO
            # /records/1/edit
            # =========================
            if (
                len(parts) == 3
                and parts[2] == "edit"
            ):

                con = db_conn()

                r = con.execute(
                    "SELECT * FROM records WHERE id=?",
                    (rid,)
                ).fetchone()

                con.close()


                if (
                    not r
                    or not can_access_record(
                        session,
                        r
                    )
                    or (
                        session["role"] == ROLE_UNIT
                        and r["status"]
                        not in (
                            STATUS_DRAFT,
                            STATUS_RETURNED
                        )
                    )
                ):

                    self.send_html(
                        base_page(
                            "403",
                            """
                            <div class='container'>
                                <div class='notice err'>
                                    Không có quyền sửa báo cáo này.
                                </div>
                            </div>
                            """,
                            session
                        ),
                        403
                    )

                    return


                self.send_html(
                    record_form_page(
                        session,
                        r
                    )
                )

                return


            # =========================
            # TRẢ BÁO CÁO CHỈNH SỬA
            # /records/1/return
            # =========================
            if (
                len(parts) == 3
                and parts[2] == "return"
            ):

                p = return_page(
                    session,
                    rid
                )

                self.send_html(
                    p
                    if p
                    else base_page(
                        "403",
                        """
                        <div class='container'>
                            <div class='notice err'>
                                Không có quyền.
                            </div>
                        </div>
                        """,
                        session
                    ),
                    200 if p else 403
                )

                return


        # =========================
        # KHÔNG TÌM THẤY TRANG
        # =========================
        self.send_html(
            base_page(
                "404",
                """
                <div class='container'>
                    <div class='notice err'>
                        Không tìm thấy trang.
                    </div>
                </div>
                """,
                session
            ),
            404
        )

        return
    def do_POST(self):

        parsed = urlparse(self.path)
        path = parsed.path

        # Reject oversized OCOP forms before reading their body. Evidence uploads
        # belong to a later phase and are deliberately not accepted here.
        if path == "/ocop" or path.startswith("/ocop/"):
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = -1
            if length < 0 or length > 256 * 1024 or self.headers.get("Transfer-Encoding"):
                self.close_connection = True
                self.send_html(base_page("Yêu cầu không hợp lệ", '<div class="container">Dữ liệu gửi không hợp lệ hoặc quá lớn.</div>'), 413)
                return
            if not self.headers.get("Content-Type", "").lower().startswith("application/x-www-form-urlencoded"):
                self.close_connection = True
                self.send_html(base_page("Yêu cầu không hợp lệ", '<div class="container">Định dạng biểu mẫu chưa được hỗ trợ.</div>'), 415)
                return

        uploaded_files = {}


        if "multipart/form-data" in self.headers.get(
            "Content-Type",
            ""
        ):

            data, uploaded_files = parse_multipart_form(self)

        else:

            data = parse_body(self)
        if path=="/login":
            username=data.get("username","").strip(); password=data.get("password","")
            con=db_conn(); u=find_user_by_username(con, username); con.close()
            if not u or not verify_password(password,u["password_hash"]): self.send_html(login_page("Tên đăng nhập hoặc mật khẩu không đúng."),401); return
            if not u["active"]: self.send_html(login_page("Tài khoản không hoạt động. Vui lòng liên hệ Chi cục để được xử lý."),401); return
            sid=new_session(u); self.redirect("/dashboard",[("Set-Cookie",f"salt_session={sid}; Path=/; HttpOnly; SameSite=Lax")]); return
        sid,session=self.require_session()
        if not session: return
        if not check_csrf(session,data): self.send_html(base_page("Lỗi","<div class='container'><div class='notice err'>Phiên làm việc không hợp lệ. Vui lòng tải lại trang.</div></div>",session),400); return
        if (path == "/users" or path.startswith("/users/") or path.rstrip("/") == "/ocop/access") and not can_manage_users(session):
            self.send_html(base_page("403", '<div class="container"><div class="notice err">Không có quyền quản lý tài khoản.</div></div>', session), 403)
            return
        if self.handle_ocop(path, parsed.query, session, data):
            return
        if path == "/import-excel":

            if not is_chi_cuc_user(session):

                self.send_html(
                    base_page(
                        "403",
                        """
                        <div class='container'>
                            <div class='notice err'>
                                Không có quyền import.
                            </div>
                        </div>
                        """,
                        session
                    ),
                    403
                )

                return


            uploaded = uploaded_files.get(
                "excel_file"
            )


            if not uploaded:

                set_flash(
                    session,
                    "err",
                    "Vui lòng chọn file Excel."
                )

                self.redirect("/import-excel")
                return


            filename = uploaded["filename"]


            if not filename.lower().endswith(".xlsx"):

                set_flash(
                    session,
                    "err",
                    "Chỉ hỗ trợ file .xlsx."
                )

                self.redirect("/import-excel")
                return


            # Giới hạn khoảng 20 MB
            if len(uploaded["content"]) > 20 * 1024 * 1024:

                set_flash(
                    session,
                    "err",
                    "File Excel quá lớn."
                )

                self.redirect("/import-excel")
                return


            report_date = data.get(
                "report_date",
                ""
            ).strip()


            sheet_name = data.get(
                "sheet_name",
                ""
            ).strip()


            try:
                session["weekly_import_preview"] = parse_weekly_workbook(
                    uploaded["content"], report_date, sheet_name, filename,
                    canonical_admin_unit,
                )
            except WeeklyImportError as exc:
                set_flash(session, "err", str(exc))
                self.redirect("/import-excel")
                return
            self.redirect("/import-excel/preview")
            return
        if path == "/import-excel/confirm":
            if not is_chi_cuc_user(session):
                self.send_html(base_page("403", "<div class='container'><div class='notice err'>Không có quyền import.</div></div>", session), 403)
                return
            preview = session.get("weekly_import_preview")
            if not preview:
                set_flash(session, "err", "Dữ liệu xem trước đã hết hạn. Hãy chọn lại file.")
                self.redirect("/import-excel")
                return
            con = db_conn()
            try:
                result = commit_weekly_preview(con, session, preview, data.get("mode", "skip"), now_text())
                con.commit()
            except WeeklyImportError as exc:
                con.rollback()
                set_flash(session, "err", str(exc))
                self.redirect("/import-excel/preview")
                return
            except INTEGRITY_ERRORS:
                con.rollback()
                set_flash(session, "err", "Dữ liệu trùng hoặc không còn hợp lệ. Hãy tải lại file để kiểm tra.")
                self.redirect("/import-excel/preview")
                return
            finally:
                con.close()
            session.pop("weekly_import_preview", None)
            set_flash(session, "ok", f"Đã import tuần {preview['week_code']}: {result['inserted']} mới, {result['updated']} cập nhật, {result['skipped']} bỏ qua.")
            self.redirect(f"/salt/weekly?week={quote(preview['week_code'])}")
            return
        if path=="/records/new":
            ok,res=save_record(session,data)
            if ok: set_flash(session,"ok","Đã lưu bản nháp."); self.redirect(f"/records/{res}")
            else: self.send_html(record_form_page(session,None,res),400)
            return
        if path=="/users/new":
            if not can_manage_users(session): self.send_html(base_page("403","<div class='container'><div class='notice err'>Không có quyền.</div></div>",session),403); return
            username=data.get("username","").strip(); password=data.get("password",""); role=data.get("role",ROLE_UNIT); unit_name=data.get("unit_name","").strip()
            if role not in tuple(ROLE_LABELS) or len(password)<6 or not username or not unit_name: set_flash(session,"err","Thông tin tài khoản chưa hợp lệ."); self.redirect("/users"); return
            con=db_conn()
            try:
                create_user(con, username, hash_password(password), role, unit_name, now_text()); con.commit(); set_flash(session,"ok","Đã tạo tài khoản.")
            except INTEGRITY_ERRORS: set_flash(session,"err","Tên đăng nhập đã tồn tại.")
            finally: con.close()
            self.redirect("/users"); return
        if path=="/change-password":
            old=data.get("old",""); new=data.get("new",""); new2=data.get("new2","")
            con=db_conn(); u=get_user(con, session["user_id"])
            if not verify_password(old,u["password_hash"]): con.close(); self.send_html(change_password_page(session,"Mật khẩu hiện tại không đúng."),400); return
            if new!=new2 or len(new)<8: con.close(); self.send_html(change_password_page(session,"Mật khẩu mới phải trùng nhau và có ít nhất 8 ký tự."),400); return
            set_user_password(con, session["user_id"], hash_password(new)); con.commit(); con.close(); set_flash(session,"ok","Đã đổi mật khẩu."); self.redirect("/dashboard"); return
        parts=[p for p in path.split('/') if p]
        if (
            len(parts) == 3
            and parts[0] == "users"
            and parts[1].isdigit()
        ):
            if not can_manage_users(session):
                self.send_html(
                    base_page(
                        "403",
                        "<div class='container'><div class='notice err'>Không có quyền.</div></div>",
                        session
                    ),
                    403
                )
                return

            uid = int(parts[1])
            action = parts[2]

            if action in ("activate", "deactivate"):
                if uid == session["user_id"] and action == "deactivate":
                    self.send_html(base_page("Không thể ngưng kích hoạt", '<div class="container">Không thể ngưng kích hoạt tài khoản đang đăng nhập.</div>', session), 400)
                    return
                con = db_conn()
                try:
                    if not get_user(con, uid):
                        self.send_error(404)
                        return
                    repositories.set_user_active(con, uid, action == "activate")
                    con.commit()
                    invalidate_user_sessions(uid)
                finally:
                    con.close()
                set_flash(session, "ok", "Đã kích hoạt lại tài khoản." if action == "activate" else "Đã ngưng kích hoạt tài khoản.")
                self.redirect("/users")
                return

            # ======================
            # SỬA TÀI KHOẢN
            # ======================
            if action == "edit":

                con = db_conn()

                user = get_user(con, uid)

                if not user:
                    con.close()
                    self.redirect("/users")
                    return

                username = data.get("username", "").strip()
                unit_name = data.get("unit_name", "").strip()
                role = data.get("role", ROLE_UNIT)
                password = data.get("password", "")
                active = 1 if data.get("active") == "1" else 0

                if not username or not unit_name:
                    con.close()
                    self.send_html(
                        user_edit_page(
                            session,
                            user,
                            "Vui lòng nhập đầy đủ thông tin."
                        ),
                        400
                    )
                    return

                if role not in tuple(ROLE_LABELS):
                    role = ROLE_UNIT

                # Không cho admin đang đăng nhập tự khóa chính mình
                if uid == session["user_id"] and (not active or role != ROLE_ADMIN):
                    con.close()
                    self.send_html(user_edit_page(session, user, "Không thể tự ngưng kích hoạt hoặc hạ quyền tài khoản đang đăng nhập."), 400)
                    return

                try:

                    new_password_hash = None
                    if password:
                        if len(password) < 6:
                            con.close()
                            self.send_html(
                                user_edit_page(
                                    session,
                                    user,
                                    "Mật khẩu phải có ít nhất 6 ký tự."
                                ),
                                400
                            )
                            return

                        new_password_hash = hash_password(password)

                    update_user_account(
                        con, uid, username, role, unit_name, active, new_password_hash
                    )

                    con.commit()
                    invalidate_user_sessions(uid)

                    set_flash(
                        session,
                        "ok",
                        "Đã cập nhật tài khoản."
                    )

                except INTEGRITY_ERRORS:
                    con.rollback()

                    set_flash(
                        session,
                        "err",
                        "Tên đăng nhập đã tồn tại."
                    )

                finally:
                    con.close()

                self.redirect("/users")
                return

            # ======================
            # XÓA / KHÓA TÀI KHOẢN
            # ======================
            if action == "delete":

                if uid == session["user_id"]:
                    set_flash(
                        session,
                        "err",
                        "Không thể xóa tài khoản đang đăng nhập."
                    )
                    self.redirect("/users")
                    return

                con = db_conn()

                user = get_user(con, uid)

                if not user:
                    con.close()
                    self.redirect("/users")
                    return

                record_count = con.execute(
                    "SELECT COUNT(*) FROM records WHERE created_by=?",
                    (uid,)
                ).fetchone()[0]

                log_count = con.execute(
                    "SELECT COUNT(*) FROM audit_logs WHERE user_id=?",
                    (uid,)
                ).fetchone()[0]

                # Nếu tài khoản đã có dữ liệu -> chỉ khóa
                if record_count > 0 or log_count > 0 or ocop_user_links(con, uid) > 0:

                    con.execute(
                        "UPDATE users SET active=0 WHERE id=?",
                        (uid,)
                    )

                    con.commit()
                    con.close()

                    set_flash(
                        session,
                        "ok",
                        "Tài khoản đã có dữ liệu nên hệ thống đã khóa thay vì xóa."
                    )

                else:

                    delete_user_account(con, uid)

                    con.commit()
                    con.close()

                    set_flash(
                        session,
                        "ok",
                        "Đã xóa tài khoản."
                    )

                invalidate_user_sessions(uid)
                self.redirect("/users")
                return
        if len(parts)>=3 and parts[0]=="records" and parts[1].isdigit():
            rid=int(parts[1]); action=parts[2]
            if action=="edit":
                con=db_conn(); r=con.execute("SELECT * FROM records WHERE id=?",(rid,)).fetchone(); con.close()
                if not r or not can_access_record(session,r): self.send_html(base_page("403","<div class='container'><div class='notice err'>Không có quyền.</div></div>",session),403); return
                ok,res=save_record(session,data,rid)
                if ok: set_flash(session,"ok","Đã cập nhật số liệu."); self.redirect(f"/records/{rid}")
                else: self.send_html(record_form_page(session,r,res),400)
                return
            con=db_conn(); r=con.execute("SELECT * FROM records WHERE id=?",(rid,)).fetchone()
            if not r or not can_access_record(session,r): con.close(); self.send_html(base_page("403","<div class='container'><div class='notice err'>Không có quyền.</div></div>",session),403); return
            if action=="submit":
                if session["role"]!=ROLE_UNIT or r["status"] not in (STATUS_DRAFT,STATUS_RETURNED): con.close(); self.send_html(base_page("Lỗi","<div class='container'><div class='notice err'>Không thể gửi báo cáo này.</div></div>",session),400); return
                con.execute("UPDATE records SET status='submitted',submitted_at=?,updated_at=? WHERE id=?",(now_text(),now_text(),rid)); add_audit(con,rid,session["user_id"],"Gửi Chi cục","Đề nghị kiểm tra/phê duyệt"); con.commit(); con.close(); set_flash(session,"ok","Đã gửi số liệu lên Chi cục."); self.redirect(f"/records/{rid}"); return
            if action=="approve":
                if not can_review_records(session) or r["status"]!=STATUS_SUBMITTED:
                    con.close()
                    self.send_html(base_page("Lỗi","<div class='container'><div class='notice err'>Không thể duyệt báo cáo này.</div></div>",session),400)
                    return
                try:
                    approved_at = now_text()
                    con.execute(
                        "UPDATE records SET status='approved',approved_at=?,reviewer_note='',updated_at=? WHERE id=?",
                        (approved_at, approved_at, rid),
                    )
                    approved_record = con.execute(
                        "SELECT * FROM records WHERE id=?",
                        (rid,),
                    ).fetchone()
                    sync_standard_salt_record(con, approved_record)
                    add_audit(
                        con, rid, session["user_id"],
                        "Phê duyệt",
                        "Chấp nhận số liệu và đồng bộ CSDL chuẩn DN_SanLuongMuoi",
                    )
                    con.commit()
                except Exception as e:
                    con.rollback()
                    con.close()
                    self.send_html(
                        base_page(
                            "Lỗi",
                            f"<div class='container'><div class='notice err'>Không thể chuẩn hóa dữ liệu khi phê duyệt: {esc(e)}</div></div>",
                            session,
                        ),
                        500,
                    )
                    return
                con.close()
                set_flash(session,"ok","Đã phê duyệt và đồng bộ dữ liệu chuẩn.")
                self.redirect(f"/records/{rid}")
                return
            if action=="return":
                if not can_review_records(session) or r["status"]!=STATUS_SUBMITTED: con.close(); self.send_html(base_page("Lỗi","<div class='container'><div class='notice err'>Không thể trả báo cáo này.</div></div>",session),400); return
                note=data.get("reviewer_note","").strip()
                if not note: con.close(); self.send_html(return_page(session,rid),400); return
                con.execute("UPDATE records SET status='returned',reviewer_note=?,updated_at=? WHERE id=?",(note,now_text(),rid)); add_audit(con,rid,session["user_id"],"Yêu cầu chỉnh sửa",note); con.commit(); con.close(); set_flash(session,"ok","Đã gửi yêu cầu chỉnh sửa cho đơn vị."); self.redirect(f"/records/{rid}"); return
            con.close()
        self.send_html(base_page("404","<div class='container'><div class='notice err'>Không tìm thấy thao tác.</div></div>",session),404)


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Hệ thống quản lý nghiệp vụ Chi cục Phát triển nông thôn")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()
    init_db()
    try:
        con_check = db_conn()
        tmp_count = con_check.execute("SELECT COUNT(*) FROM DM_DonViHanhChinh WHERE Ma_DonViHanhChinh LIKE 'TMP%'").fetchone()[0]
        official_count = con_check.execute(
            "SELECT COUNT(*) FROM DM_DonViHanhChinh WHERE Ma_DonViHanhChinh IN (?,?,?,?,?,?,?,?)",
            tuple(code for code, _level in OFFICIAL_ADMIN_UNITS.values()),
        ).fetchone()[0]
        con_check.close()
        synced = sync_all_approved_records()
        print(f"Đã đồng bộ dữ liệu chuẩn từ {synced} báo cáo đã duyệt.")
        print(f"Danh mục hành chính chính thức: {official_count}/8 đơn vị; mã TMP còn lại: {tmp_count}.")
    except Exception as e:
        print(f"Cảnh báo: chưa đồng bộ được dữ liệu chuẩn: {e}")
    server=ThreadingHTTPServer((args.host,args.port),Handler)
    print("="*72)
    print("HỆ THỐNG QUẢN LÝ NGHIỆP VỤ CHI CỤC PHÁT TRIỂN NÔNG THÔN")
    settings = load_settings()
    print(f"Database PostgreSQL: {settings.dbname} @ {settings.host}:{settings.port}")
    print(f"Đang chạy tại: http://127.0.0.1:{args.port}")
    print(f"Trong mạng LAN: http://<IP-máy-chủ>:{args.port}")
    print("Tài khoản demo Chi cục: chicuc / 123456")
    print("Nhấn Ctrl+C để dừng.")
    print("="*72)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nĐã dừng máy chủ.")
    finally:
        server.server_close()

if __name__=="__main__":
    main()
