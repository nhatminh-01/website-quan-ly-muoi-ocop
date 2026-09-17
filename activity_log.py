"""Activity/audit helpers for internal Chi cuc users."""
from __future__ import annotations

from datetime import datetime
from html import escape
import math
import re
from urllib.parse import parse_qs, urlencode


MODULE_LABELS = {
    "auth": "Đăng nhập",
    "account": "Tài khoản",
    "profile": "Thông tin cá nhân",
    "diem_nghiep": "Diêm nghiệp",
    "ocop": "OCOP",
    "admin_units": "Danh mục hành chính",
    "system": "Hệ thống",
}

ACTION_LABELS = {
    "login": "Đăng nhập",
    "logout": "Đăng xuất",
    "profile_update": "Cập nhật thông tin cá nhân",
    "password_change": "Đổi mật khẩu",
    "account_create": "Tạo tài khoản",
    "account_update": "Sửa tài khoản",
    "account_activate": "Kích hoạt tài khoản",
    "account_deactivate": "Ngưng kích hoạt tài khoản",
    "weekly_import_upload": "Tải file báo cáo tuần",
    "weekly_import_preview": "Xem trước báo cáo tuần",
    "weekly_import_confirm": "Xác nhận import báo cáo tuần",
    "weekly_export": "Xuất Excel Diêm nghiệp",
    "ocop_import_upload": "Tải file OCOP",
    "ocop_import_preview": "Xem trước import OCOP",
    "ocop_import_publish": "Xác nhận import OCOP",
    "ocop_export": "Xuất Excel OCOP",
    "admin_unit_update": "Cập nhật danh mục hành chính",
}


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _snapshot(con, user_id):
    if not user_id:
        return {"username": "", "role": "", "full_name": "", "department": ""}
    row = con.execute(
        """SELECT u.username,u.role,
                  COALESCE(p.full_name,'') AS full_name,
                  COALESCE(p.department,'') AS department
           FROM app.users u
           LEFT JOIN app.user_profiles p ON p.user_id=u.id
           WHERE u.id=?""",
        (user_id,),
    ).fetchone()
    if not row:
        return {"username": "", "role": "", "full_name": "", "department": ""}
    return dict(row)


def write_activity(
    con,
    user_id,
    action,
    detail="",
    *,
    module="system",
    object_type=None,
    object_id=None,
    record_id=None,
    success=True,
    ip_address="",
    user_agent="",
):
    """Append one immutable activity row. Never store passwords/tokens in detail."""
    snap = _snapshot(con, user_id)
    con.execute(
        """INSERT INTO app.audit_logs(
               record_id,user_id,action,detail,created_at,module,object_type,object_id,
               username_snapshot,full_name_snapshot,role_snapshot,department_snapshot,
               success,ip_address,user_agent
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            record_id,
            user_id,
            str(action or ""),
            str(detail or "")[:2000],
            now_text(),
            str(module or "system")[:50],
            str(object_type)[:100] if object_type else None,
            str(object_id)[:255] if object_id is not None else None,
            snap["username"],
            snap["full_name"],
            snap["role"],
            snap["department"],
            bool(success),
            str(ip_address or "")[:64] or None,
            str(user_agent or "")[:1000] or None,
        ),
    )


def add_record_audit(con, record_id, user_id, action, detail=""):
    """Drop-in replacement for server.add_audit with richer snapshots."""
    write_activity(
        con,
        user_id,
        action,
        detail,
        module="diem_nghiep",
        object_type="record",
        object_id=record_id,
        record_id=record_id,
        success=True,
    )


def _esc(value):
    return escape("" if value is None else str(value), quote=True)


def _date_label(value):
    text = str(value or "")
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).strftime("%d/%m/%Y %H:%M:%S")
    except ValueError:
        return text


def _action_label(value):
    text = str(value or "")
    return ACTION_LABELS.get(text, text or "—")


def _module_label(value):
    text = str(value or "")
    return MODULE_LABELS.get(text, text or "Hệ thống")


def _admin_filter_options(con, selected_user):
    rows = con.execute(
        """SELECT u.id,u.username,COALESCE(p.full_name,'') AS full_name
           FROM app.users u LEFT JOIN app.user_profiles p ON p.user_id=u.id
           WHERE u.role IN ('admin','staff') ORDER BY COALESCE(NULLIF(p.full_name,''),u.username),u.id"""
    ).fetchall()
    options = ['<option value="">Tất cả người dùng</option>']
    for row in rows:
        label = row["full_name"] or row["username"]
        value = str(row["id"])
        options.append(
            f'<option value="{_esc(value)}"{" selected" if value == selected_user else ""}>{_esc(label)} ({_esc(row["username"])})</option>'
        )
    return "".join(options)


def activity_page(con, session, query_string=""):
    params = parse_qs(query_string or "")
    is_admin = session.get("role") == "admin"
    page = max(1, int((params.get("page") or ["1"])[0] or 1))
    page_size = 30
    selected_user = ((params.get("user") or [""])[0]).strip() if is_admin else str(session["user_id"])
    selected_module = ((params.get("module") or [""])[0]).strip()
    selected_success = ((params.get("success") or [""])[0]).strip()
    date_from = ((params.get("from") or [""])[0]).strip()
    date_to = ((params.get("to") or [""])[0]).strip()

    where = []
    values = []
    if is_admin:
        if selected_user.isdigit():
            where.append("a.user_id=?")
            values.append(int(selected_user))
    else:
        where.append("a.user_id=?")
        values.append(session["user_id"])
    if selected_module:
        where.append("a.module=?")
        values.append(selected_module)
    if selected_success in ("1", "0"):
        where.append("a.success=?")
        values.append(selected_success == "1")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_from):
        where.append("a.created_at>=?")
        values.append(date_from + " 00:00:00")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_to):
        where.append("a.created_at<=?")
        values.append(date_to + " 23:59:59")
    clause = (" WHERE " + " AND ".join(where)) if where else ""

    total = con.execute("SELECT COUNT(*) FROM app.audit_logs a" + clause, tuple(values)).fetchone()[0]
    pages = max(1, math.ceil(total / page_size))
    page = min(page, pages)
    offset = (page - 1) * page_size
    rows = con.execute(
        """SELECT a.id,a.user_id,a.action,a.detail,a.created_at,a.module,a.object_type,a.object_id,a.success,
                  COALESCE(a.username_snapshot,u.username,'') AS username,
                  COALESCE(NULLIF(a.full_name_snapshot,''),NULLIF(p.full_name,''),u.username,'') AS full_name,
                  COALESCE(NULLIF(a.department_snapshot,''),p.department,'') AS department
           FROM app.audit_logs a
           LEFT JOIN app.users u ON u.id=a.user_id
           LEFT JOIN app.user_profiles p ON p.user_id=a.user_id"""
        + clause
        + " ORDER BY a.created_at DESC,a.id DESC LIMIT ? OFFSET ?",
        tuple(values + [page_size, offset]),
    ).fetchall()

    tr = []
    for row in rows:
        result = '<span class="activity-status ok">Thành công</span>' if row["success"] else '<span class="activity-status fail">Thất bại</span>'
        user_cell = f'{_esc(row["full_name"])}<br><small class="muted">{_esc(row["username"])}</small>' if is_admin else _esc(row["full_name"])
        detail = _esc(row["detail"] or "—")
        tr.append(
            f'<tr><td>{_esc(_date_label(row["created_at"]))}</td><td>{user_cell}</td><td>{_esc(row["department"] or "—")}</td>'
            f'<td>{_esc(_module_label(row["module"]))}</td><td>{_esc(_action_label(row["action"]))}</td><td>{detail}</td><td>{result}</td></tr>'
        )
    rows_html = "".join(tr) or '<tr><td colspan="7" class="empty">Chưa có lịch sử hoạt động phù hợp.</td></tr>'

    module_options = ['<option value="">Tất cả phân hệ</option>'] + [
        f'<option value="{_esc(key)}"{" selected" if selected_module == key else ""}>{_esc(label)}</option>'
        for key, label in MODULE_LABELS.items()
    ]
    user_filter = ""
    if is_admin:
        user_filter = f'<div class="field"><label>Người dùng</label><select name="user">{_admin_filter_options(con, selected_user)}</select></div>'
    filters = f'''<form class="card activity-filters" method="get" action="/activity">
      {user_filter}
      <div class="field"><label>Phân hệ</label><select name="module">{"".join(module_options)}</select></div>
      <div class="field"><label>Kết quả</label><select name="success"><option value="">Tất cả</option><option value="1"{" selected" if selected_success == "1" else ""}>Thành công</option><option value="0"{" selected" if selected_success == "0" else ""}>Thất bại</option></select></div>
      <div class="field"><label>Từ ngày</label><input type="date" name="from" value="{_esc(date_from)}"></div>
      <div class="field"><label>Đến ngày</label><input type="date" name="to" value="{_esc(date_to)}"></div>
      <div class="actions"><button class="btn primary">Lọc</button><a class="btn" href="/activity">Xóa lọc</a></div>
    </form>'''

    base_params = {}
    if is_admin and selected_user:
        base_params["user"] = selected_user
    if selected_module:
        base_params["module"] = selected_module
    if selected_success:
        base_params["success"] = selected_success
    if date_from:
        base_params["from"] = date_from
    if date_to:
        base_params["to"] = date_to
    prev_link = ""
    next_link = ""
    if page > 1:
        prev_link = f'<a class="btn small" href="/activity?{urlencode({**base_params, "page": page - 1})}">← Trang trước</a>'
    if page < pages:
        next_link = f'<a class="btn small" href="/activity?{urlencode({**base_params, "page": page + 1})}">Trang sau →</a>'
    pagination = f'<div class="activity-pagination">{prev_link}<span class="muted">Trang {page}/{pages} · {total} lượt thao tác</span>{next_link}</div>'
    scope_note = "Toàn hệ thống" if is_admin else "Chỉ hoạt động của tài khoản đang đăng nhập"
    return f'''<div class="container activity-page">
      <div class="page-head"><div><h1>Lịch sử hoạt động</h1><div class="subtitle">{_esc(scope_note)}. Nhật ký chỉ đọc, không chỉnh sửa hoặc xóa trên giao diện.</div></div></div>
      {filters}
      <section class="card"><div class="table-wrap"><table class="summary-table activity-table"><thead><tr><th>Thời gian</th><th>Người dùng</th><th>Phòng/Bộ phận</th><th>Phân hệ</th><th>Thao tác</th><th>Nội dung</th><th>Kết quả</th></tr></thead><tbody>{rows_html}</tbody></table></div>{pagination}</section>
    </div>'''


def describe_request(path, method="POST"):
    """Return module/action/detail for important routes that do not call server.add_audit."""
    path = str(path or "")
    method = str(method or "GET").upper()
    if method == "POST":
        exact = {
            "/import-excel": ("diem_nghiep", "weekly_import_upload", "Tải file báo cáo tuần"),
            "/import-excel/preview": ("diem_nghiep", "weekly_import_preview", "Xem trước dữ liệu báo cáo tuần"),
            "/import-excel/confirm": ("diem_nghiep", "weekly_import_confirm", "Xác nhận import báo cáo tuần"),
            "/ocop/import": ("ocop", "ocop_import_upload", "Tải file dữ liệu OCOP"),
            "/ocop/import/preview": ("ocop", "ocop_import_preview", "Xem trước dữ liệu OCOP"),
            "/ocop/import/confirm": ("ocop", "ocop_import_publish", "Xác nhận import dữ liệu OCOP"),
            "/users/new": ("account", "account_create", "Tạo tài khoản nội bộ Chi cục"),
            "/change-password": ("account", "password_change", "Đổi mật khẩu tài khoản"),
        }
        if path in exact:
            return exact[path]
        if re.fullmatch(r"/users/\d+/edit", path):
            return "account", "account_update", "Cập nhật tài khoản nội bộ Chi cục"
        if re.fullmatch(r"/users/\d+/activate", path):
            return "account", "account_activate", "Kích hoạt tài khoản"
        if re.fullmatch(r"/users/\d+/deactivate", path):
            return "account", "account_deactivate", "Ngưng kích hoạt tài khoản"
        if path.startswith("/admin-units"):
            return "admin_units", "admin_unit_update", "Cập nhật danh mục đơn vị hành chính"
    if method == "GET":
        if path in ("/export.xlsx", "/records/export.xlsx"):
            return "diem_nghiep", "weekly_export", "Xuất Excel dữ liệu Diêm nghiệp"
        if path == "/ocop/export.xlsx":
            return "ocop", "ocop_export", "Xuất Excel dữ liệu OCOP"
    return None
