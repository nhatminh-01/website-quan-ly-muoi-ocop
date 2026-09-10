"""OCOP stage 1 business rules, scoped queries and atomic audit history.

The caller owns the connection. No server globals or database paths are used.
"""
from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Mapping
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from functools import wraps
import json
import re
import secrets
import sqlite3
from permissions import ROLE_LABELS, is_chi_cuc_user

try:
    import psycopg
except ImportError:  # Legacy SQLite-only test/runtime.
    psycopg = None


class OcopError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


APP_STATUSES = ("draft", "submitted", "checking", "returned", "eligible", "scoring", "completed", "cancelled")
EVALUATION_TYPES = ("new", "re_evaluation", "upgrade")
LOCKED_STATUSES = ("submitted", "checking", "eligible", "scoring", "completed")
OPEN_STATUSES = ("draft", "submitted", "checking", "returned", "eligible", "scoring")


def _json_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"Unsupported snapshot value: {type(value).__name__}")


def _now():
    return datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d %H:%M:%S.%f")


def _value(data, key, default=""):
    value = data.get(key, default)
    if isinstance(value, (list, tuple)):
        value = value[0] if value else default
    return default if value is None else value


def _text(data, key, maximum=255, required=False, default=""):
    value = str(_value(data, key, default)).strip()
    if required and not value:
        raise OcopError("Vui lòng nhập đầy đủ trường bắt buộc.")
    if len(value) > maximum or "\x00" in value:
        raise OcopError("Nội dung quá dài hoặc có ký tự không hợp lệ.")
    return value


def _number(value, minimum=1, maximum=2147483647):
    try:
        result = int(str(value))
    except (ValueError, TypeError):
        raise OcopError("Giá trị số không hợp lệ.") from None
    if result < minimum or result > maximum:
        raise OcopError("Giá trị số nằm ngoài phạm vi cho phép.")
    return result


def _one(con, sql, args=()):
    cursor = con.execute(sql, args)
    row = cursor.fetchone()
    if row is None:
        return None
    if isinstance(row, Mapping):
        return dict(row)
    return dict(zip((col[0] for col in cursor.description), row))


def _all(con, sql, args=()):
    cursor = con.execute(sql, args)
    names = [col[0] for col in cursor.description]
    return [dict(row) if isinstance(row, Mapping) else dict(zip(names, row))
            for row in cursor.fetchall()]


@contextmanager
def _transaction(con):
    nested = con.in_transaction
    savepoint = "ocop_" + secrets.token_hex(6)
    try:
        con.execute("SAVEPOINT " + savepoint if nested else "BEGIN IMMEDIATE")
        yield
        con.execute("RELEASE SAVEPOINT " + savepoint) if nested else con.commit()
    except Exception:
        if nested:
            con.execute("ROLLBACK TO SAVEPOINT " + savepoint)
            con.execute("RELEASE SAVEPOINT " + savepoint)
        else:
            con.rollback()
        raise


def _mutation(fn):
    @wraps(fn)
    def execute(con, session, *args, **kwargs):
        try:
            with _transaction(con):
                get_scope(con, session)
                return fn(con, session, *args, **kwargs)
        except tuple(error for error in (sqlite3.IntegrityError,
                                         getattr(psycopg, "IntegrityError", None)) if error):
            raise OcopError("Dữ liệu bị trùng hoặc không còn phù hợp. Vui lòng tải lại và kiểm tra.", 409) from None
        except tuple(error for error in (sqlite3.Error,
                                         getattr(psycopg, "Error", None)) if error):
            raise OcopError("Không thể lưu dữ liệu lúc này. Vui lòng thử lại.", 503) from None
    return execute


def get_scope(con, session):
    """Return the current authorized unit code, or None for an active admin."""
    if not isinstance(session, dict) or not session.get("user_id"):
        raise OcopError("Vui lòng đăng nhập để sử dụng OCOP.", 403)
    user = _one(con, "SELECT id,role,active FROM users WHERE id=?", (session["user_id"],))
    if not user or not user["active"] or user["role"] not in ROLE_LABELS:
        raise OcopError("Tài khoản không có quyền sử dụng OCOP.", 403)
    if session.get("role") != user["role"]:
        raise OcopError("Quyền tài khoản đã thay đổi. Vui lòng đăng nhập lại.", 403)
    if is_chi_cuc_user(user):
        return None
    unit = _one(con, """SELECT d.Ma_DonViHanhChinh AS code FROM user_admin_units m
        JOIN DM_DonViHanhChinh d ON d.Ma_DonViHanhChinh=m.ma_don_vi_hanh_chinh
        WHERE m.user_id=? AND d.TinhTrang=1 AND d.CapHanhChinh IN ('xa','phuong')
        AND upper(d.Ma_DonViHanhChinh) NOT LIKE 'TMP%'""", (user["id"],))
    if not unit:
        raise OcopError("Tài khoản chưa được gán mã xã/phường đang hoạt động. Liên hệ quản trị viên.", 403)
    return unit["code"]


def unit_options(con, session):
    scope = get_scope(con, session)
    sql = "SELECT Ma_DonViHanhChinh AS code,TenDonVi AS name FROM DM_DonViHanhChinh WHERE TinhTrang=1 AND CapHanhChinh IN ('xa','phuong') AND upper(Ma_DonViHanhChinh) NOT LIKE 'TMP%'"
    args = []
    if scope is not None:
        sql += " AND Ma_DonViHanhChinh=?"
        args.append(scope)
    return _all(con, sql + " ORDER BY TenDonVi,Ma_DonViHanhChinh", args)


def _check_unit(con, session, code):
    scope = get_scope(con, session)
    if scope is not None and code != scope:
        raise OcopError("Không có quyền thao tác dữ liệu của xã/phường khác.", 403)
    unit = _one(con, "SELECT Ma_DonViHanhChinh FROM DM_DonViHanhChinh WHERE Ma_DonViHanhChinh=? AND TinhTrang=1 AND CapHanhChinh IN ('xa','phuong') AND upper(Ma_DonViHanhChinh) NOT LIKE 'TMP%'", (code,))
    if not unit:
        raise OcopError("Vui lòng chọn mã xã/phường đang hoạt động.")
    return code


ENTITY_SELECT = """SELECT e.*,c.TenCoSo AS name,c.LoaiCoSo AS facility_type,c.DiaChi AS address,
    c.Ma_DonViHanhChinh AS ma_don_vi_hanh_chinh,d.TenDonVi AS unit_name,
    CASE WHEN e.archived_at IS NULL THEN 'active' ELSE 'archived' END AS status
    FROM ocop_entities e JOIN DM_CoSo c ON c.Ma_CoSo=e.ma_co_so
    JOIN DM_DonViHanhChinh d ON d.Ma_DonViHanhChinh=c.Ma_DonViHanhChinh"""
PRODUCT_SELECT = """SELECT p.*,p.ten_san_pham AS name,c.TenCoSo AS entity_name,d.TenDonVi AS unit_name,
    e.id AS entity_id,e.archived_at AS entity_archived_at,
    cs.code AS criteria_set_code,cs.name AS criteria_set_name,cs.product_category AS criteria_category,
    cs.product_group AS criteria_group,cs.product_subgroup AS criteria_subgroup,
    cs.legal_document AS criteria_legal_document,cs.version AS criteria_version,
    cs.effective_from AS criteria_effective_from,cs.active AS criteria_set_active
    FROM ocop_products p JOIN DM_CoSo c ON c.Ma_CoSo=p.ma_co_so
    JOIN ocop_entities e ON e.ma_co_so=p.ma_co_so
    JOIN DM_DonViHanhChinh d ON d.Ma_DonViHanhChinh=p.ma_don_vi_hanh_chinh
    LEFT JOIN ocop_criteria_sets cs ON cs.id=p.criteria_set_id"""
APPLICATION_SELECT = """SELECT a.*,p.ten_san_pham AS product_name,p.ma_san_pham,p.ma_co_so,
    p.ma_don_vi_hanh_chinh,p.product_group,c.TenCoSo AS entity_name,d.TenDonVi AS unit_name,
    cs.code AS criteria_set_code,cs.name AS criteria_set_name,cs.product_category AS criteria_category,
    cs.product_group AS criteria_group,cs.product_subgroup AS criteria_subgroup,
    cs.legal_document AS criteria_legal_document,cs.version AS criteria_version,
    cs.effective_from AS criteria_effective_from,cs.active AS criteria_set_active,
    u.username AS reviewer_name
    FROM ocop_applications a JOIN ocop_products p ON p.id=a.product_id
    JOIN DM_CoSo c ON c.Ma_CoSo=p.ma_co_so
    JOIN DM_DonViHanhChinh d ON d.Ma_DonViHanhChinh=p.ma_don_vi_hanh_chinh
    LEFT JOIN ocop_criteria_sets cs ON cs.id=a.criteria_set_id
    LEFT JOIN users u ON u.id=a.reviewer_id"""


def _get(con, session, object_id, select, id_column, unit_column):
    scope = get_scope(con, session)
    sql = select + " WHERE " + id_column + "=?"
    args = [_number(object_id)]
    if scope is not None:
        sql += " AND " + unit_column + "=?"
        args.append(scope)
    row = _one(con, sql, args)
    if not row:
        raise OcopError("Không tìm thấy dữ liệu hoặc bạn không có quyền truy cập.", 404)
    return row


def get_entity(con, session, object_id):
    return _get(con, session, object_id, ENTITY_SELECT, "e.id", "c.Ma_DonViHanhChinh")


def get_product(con, session, object_id):
    return _get(con, session, object_id, PRODUCT_SELECT, "p.id", "p.ma_don_vi_hanh_chinh")


def get_application(con, session, object_id):
    return _get(con, session, object_id, APPLICATION_SELECT, "a.id", "p.ma_don_vi_hanh_chinh")


def _criteria_set_by_id(con, session, object_id, require_active=False):
    get_scope(con, session)
    row = _one(con, """SELECT id,code,name,product_category,product_group,product_subgroup,
        legal_document,version,effective_from,effective_to,max_score,active,sort_order,notes
        FROM ocop_criteria_sets WHERE id=?""", (_number(object_id),))
    if not row:
        raise OcopError("Không tìm thấy bộ tiêu chí OCOP.", 404)
    if require_active and not row["active"]:
        raise OcopError("Bộ tiêu chí OCOP đã ngừng áp dụng.", 409)
    return row


def get_criteria_set(con, session, object_id):
    return _criteria_set_by_id(con, session, object_id)


def criteria_set_options(con, session, active_only=True):
    get_scope(con, session)
    sql = """SELECT id,code,name,product_category,product_group,product_subgroup,
        legal_document,version,effective_from,max_score,active,sort_order
        FROM ocop_criteria_sets"""
    if active_only:
        sql += " WHERE active=1"
    return _all(con, sql + " ORDER BY sort_order,id")


def list_criteria_sets(con, session, filters=None):
    get_scope(con, session)
    filters = filters or {}
    where, args = ["1=1"], []
    query = _text(filters, "q", 200)
    if query:
        pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where.append("(code LIKE ? ESCAPE '\\' OR name LIKE ? ESCAPE '\\' OR product_category LIKE ? ESCAPE '\\' OR product_group LIKE ? ESCAPE '\\')")
        args.extend([pattern] * 4)
    category = _text(filters, "category", 150)
    if category:
        where.append("product_category=?")
        args.append(category)
    rows = _all(con, """SELECT id,code,name,product_category,product_group,product_subgroup,
        legal_document,version,effective_from,effective_to,max_score,active,sort_order,notes
        FROM ocop_criteria_sets WHERE """ + " AND ".join(where) + " ORDER BY sort_order,id", args)
    return {"items": rows, "total": len(rows)}


def criteria_categories(con, session):
    get_scope(con, session)
    return _all(con, "SELECT product_category AS name FROM ocop_criteria_sets WHERE active=1 GROUP BY product_category ORDER BY MIN(sort_order),product_category")


def get_criteria_tree(con, session, object_id):
    criteria_set = _criteria_set_by_id(con, session, object_id)
    rows = _all(con, """SELECT id,criteria_set_id,parent_id,code,title,item_type,section_code,
        max_score,requirement_text,sort_order,active
        FROM ocop_criteria WHERE criteria_set_id=? AND active=1
        ORDER BY sort_order,id""", (criteria_set["id"],))
    options = _all(con, """SELECT o.id,o.criterion_id,o.label,o.score,o.min_star,o.is_eliminating,
        o.evidence_hint,o.sort_order,o.active FROM ocop_criteria_options o
        JOIN ocop_criteria c ON c.id=o.criterion_id
        WHERE c.criteria_set_id=? AND o.active=1 ORDER BY o.criterion_id,o.sort_order,o.id""",
        (criteria_set["id"],))
    by_criterion = {}
    for option in options:
        by_criterion.setdefault(option["criterion_id"], []).append(option)
    for row in rows:
        row["options"] = by_criterion.get(row["id"], [])
    return {"criteria_set": criteria_set, "criteria": rows, "option_count": len(options)}


def _listing(con, session, filters, select, unit_column, search_columns, status_column, order_columns, extra=()):
    filters = filters or {}
    scope = get_scope(con, session)
    where, args = ["1=1"], []
    selected_unit = _text(filters, "unit", 10, default=_value(filters, "ma_don_vi_hanh_chinh", ""))
    if selected_unit:
        _check_unit(con, session, selected_unit)
    if scope is not None or selected_unit:
        where.append(unit_column + "=?")
        args.append(scope or selected_unit)
    query = _text(filters, "q", 200)
    if query:
        pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where.append("(" + " OR ".join(column + " LIKE ? ESCAPE '\\'" for column in search_columns) + ")")
        args.extend([pattern] * len(search_columns))
    status = _text(filters, "status", 30)
    if status and status != "all":
        if status not in APP_STATUSES + ("active", "archived"):
            raise OcopError("Trạng thái lọc không hợp lệ.")
        where.append(status_column + "=?")
        args.append(status)
    for key, column, kind in extra:
        value = _text(filters, key, 100)
        if value:
            if kind == "year":
                value = _number(value, 2000, 2100)
            where.append(column + "=?")
            args.append(value)
    page = _number(_value(filters, "page", 1), 1, 10000000)
    size = _number(_value(filters, "page_size", _value(filters, "limit", 20)), 1, 200)
    sort = _text(filters, "sort", 30, default="updated_at")
    if sort not in order_columns:
        sort = "updated_at"
    direction = "ASC" if _text(filters, "order", 4).lower() == "asc" else "DESC"
    sql = select + " WHERE " + " AND ".join(where)
    total = _one(con, "SELECT COUNT(*) AS n FROM (" + sql + ")", args)["n"]
    pages = max(1, (total + size - 1) // size)
    page = min(page, pages)
    items = _all(con, sql + " ORDER BY " + order_columns[sort] + " " + direction + ",id DESC LIMIT ? OFFSET ?", args + [size, (page - 1) * size])
    return {"items": items, "total": total, "page": page, "pages": pages, "page_size": size}


def list_entities(con, session, filters=None):
    return _listing(con, session, filters, ENTITY_SELECT, "c.Ma_DonViHanhChinh",
        ("c.TenCoSo", "e.ma_co_so", "e.tax_code"), "CASE WHEN e.archived_at IS NULL THEN 'active' ELSE 'archived' END",
        {"updated_at": "e.updated_at", "name": "c.TenCoSo", "created_at": "e.created_at"})


def list_products(con, session, filters=None):
    return _listing(con, session, filters, PRODUCT_SELECT, "p.ma_don_vi_hanh_chinh",
        ("p.ten_san_pham", "p.ma_san_pham", "c.TenCoSo"), "p.status",
        {"updated_at": "p.updated_at", "name": "p.ten_san_pham", "created_at": "p.created_at"}, (("group", "p.product_group", "text"),))


def list_applications(con, session, filters=None):
    return _listing(con, session, filters, APPLICATION_SELECT, "p.ma_don_vi_hanh_chinh",
        ("p.ten_san_pham", "p.ma_san_pham", "c.TenCoSo"), "a.status",
        {"updated_at": "a.updated_at", "name": "p.ten_san_pham", "created_at": "a.created_at", "year": "a.year"},
        (("group", "p.product_group", "text"), ("year", "a.year", "year")))


def dashboard(con, session, filters=None):
    filters = filters or {}
    scope = get_scope(con, session)
    selected_unit = _text(filters, "unit", 10)
    if selected_unit:
        _check_unit(con, session, selected_unit)
    selected_unit = scope or selected_unit
    args = [selected_unit] if selected_unit else []
    entity_where = " AND c.Ma_DonViHanhChinh=?" if selected_unit else ""
    product_where = " AND p.ma_don_vi_hanh_chinh=?" if selected_unit else ""
    result = {"entities": _one(con, "SELECT COUNT(*) n FROM ocop_entities e JOIN DM_CoSo c ON c.Ma_CoSo=e.ma_co_so WHERE e.archived_at IS NULL" + entity_where, args)["n"],
              "products": _one(con, "SELECT COUNT(*) n FROM ocop_products p WHERE p.status='active'" + product_where, args)["n"]}
    application_where, application_args = product_where, list(args)
    if _text(filters, "year", 10):
        application_where += " AND a.year=?"
        application_args.append(_number(_value(filters, "year"), 2000, 2100))
    statuses = _all(con, "SELECT a.status,COUNT(*) n FROM ocop_applications a JOIN ocop_products p ON p.id=a.product_id WHERE 1=1" + application_where + " GROUP BY a.status", application_args)
    result.update({status: 0 for status in APP_STATUSES})
    result.update({row["status"]: row["n"] for row in statuses})
    result["applications"] = sum(row["n"] for row in statuses)
    result["drafts"] = result["draft"]
    return result


def entity_options(con, session):
    scope = get_scope(con, session)
    return _all(con, """SELECT e.ma_co_so,c.TenCoSo AS name,d.TenDonVi AS unit_name
        FROM ocop_entities e JOIN DM_CoSo c ON c.Ma_CoSo=e.ma_co_so
        JOIN DM_DonViHanhChinh d ON d.Ma_DonViHanhChinh=c.Ma_DonViHanhChinh
        WHERE e.archived_at IS NULL AND d.TinhTrang=1"""
        + (" AND c.Ma_DonViHanhChinh=?" if scope is not None else "")
        + " ORDER BY c.TenCoSo,e.id", [scope] if scope is not None else [])


def product_options(con, session):
    scope = get_scope(con, session)
    return _all(con, """SELECT p.id,p.ten_san_pham AS name,c.TenCoSo AS entity_name,
        p.criteria_set_id,cs.code AS criteria_set_code,cs.name AS criteria_set_name
        FROM ocop_products p JOIN ocop_entities e ON e.ma_co_so=p.ma_co_so
        JOIN DM_CoSo c ON c.Ma_CoSo=p.ma_co_so
        LEFT JOIN ocop_criteria_sets cs ON cs.id=p.criteria_set_id
        WHERE p.status='active' AND e.archived_at IS NULL AND p.criteria_set_id IS NOT NULL
          AND cs.active=1"""
        + (" AND p.ma_don_vi_hanh_chinh=?" if scope is not None else "")
        + " ORDER BY p.ten_san_pham,p.id", [scope] if scope is not None else [])


def get_reviews(con, session, application_id):
    application = get_application(con, session, application_id)
    return _all(con, """SELECT r.*,u.username AS username,u.username AS user_name FROM ocop_reviews r
        LEFT JOIN users u ON u.id=r.reviewer_id WHERE r.application_id=? ORDER BY r.created_at DESC,r.id DESC""", (application["id"],))


def _audit(con, session, kind, object_id, action, detail, when):
    payload = detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False, sort_keys=True, default=_json_value)
    con.execute("""INSERT INTO audit_logs(record_id,user_id,action,detail,created_at,module,object_type,object_id)
        VALUES(NULL,?,?,?,?, 'ocop',?,?)""", (session["user_id"], action, payload, when, kind, str(object_id)))


def _review(con, session, application_id, action, comment, when):
    con.execute("INSERT INTO ocop_reviews(application_id,reviewer_id,action,comment,created_at) VALUES(?,?,?,?,?)", (application_id, session["user_id"], action, comment, when))


def _version(row, data, key="updated_at"):
    supplied = _value(data, key, None)
    if supplied is None or str(supplied) != str(row[key]):
        raise OcopError("Dữ liệu đã thay đổi hoặc thiếu phiên bản. Vui lòng tải lại trang trước khi lưu.", 409)


def _lock_check(con, product_id=None, ma_co_so=None, archive=False):
    statuses = OPEN_STATUSES + ("completed",) if archive else LOCKED_STATUSES
    sql = "SELECT a.id FROM ocop_applications a JOIN ocop_products p ON p.id=a.product_id WHERE a.status IN (" + ",".join("?" for _ in statuses) + ")"
    args = list(statuses)
    sql += " AND p.id=?" if product_id is not None else " AND p.ma_co_so=?"
    args.append(product_id if product_id is not None else ma_co_so)
    if _one(con, sql + " LIMIT 1", args):
        raise OcopError("Dữ liệu đang liên kết với hồ sơ cần được bảo toàn. Không thể sửa hoặc lưu trữ lúc này.", 409)


def _code(data, key, prefix):
    value = _text(data, key, 10)
    if value and not re.fullmatch(r"[A-Za-z0-9_-]{1,10}", value):
        raise OcopError("Mã chỉ được gồm chữ, số, dấu gạch ngang/gạch dưới và tối đa 10 ký tự.")
    return value or prefix + secrets.token_hex(4).upper()


def _entity_values(data):
    values = {key: _text(data, key, maximum, required) for key, maximum, required in (
        ("name", 255, True), ("facility_type", 100, True), ("address", 255, True),
        ("phone", 50, False), ("email", 254, False), ("tax_code", 50, False),
        ("website", 500, False), ("description", 5000, False))}
    values["representative_name"] = _text(data, "representative_name", 255, default=_value(data, "rep", ""))
    if values["email"] and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", values["email"]):
        raise OcopError("Địa chỉ email không hợp lệ.")
    if values["website"] and not re.match(r"^https?://", values["website"], re.I):
        raise OcopError("Địa chỉ website cần bắt đầu bằng http:// hoặc https://.")
    return values


@_mutation
def create_entity(con, session, data):
    values = _entity_values(data)
    scope = get_scope(con, session)
    unit = _text(data, "ma_don_vi_hanh_chinh", 10, default=scope or "")
    _check_unit(con, session, unit)
    code, when = _code(data, "ma_co_so", "C"), _now()
    con.execute("INSERT INTO DM_CoSo(Ma_CoSo,TenCoSo,LoaiCoSo,DiaChi,Ma_DonViHanhChinh) VALUES(?,?,?,?,?)", (code, values["name"], values["facility_type"], values["address"], unit))
    cursor = con.execute("""INSERT INTO ocop_entities(ma_co_so,representative_name,phone,email,tax_code,website,description,created_by,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?)""", (code, values["representative_name"], values["phone"], values["email"], values["tax_code"], values["website"], values["description"], session["user_id"], when, when))
    object_id = cursor.lastrowid
    _audit(con, session, "entity", object_id, "create", {"ma_co_so": code, "unit": unit, "values": values}, when)
    return get_entity(con, session, object_id)


@_mutation
def update_entity(con, session, object_id, data):
    row = get_entity(con, session, object_id)
    _version(row, data)
    if row["archived_at"]:
        raise OcopError("Chủ thể đã được lưu trữ.", 409)
    _lock_check(con, ma_co_so=row["ma_co_so"])
    values = _entity_values(data)
    unit = _text(data, "ma_don_vi_hanh_chinh", 10, default=row["ma_don_vi_hanh_chinh"])
    _check_unit(con, session, unit)
    if unit != row["ma_don_vi_hanh_chinh"] and _one(con, "SELECT a.id FROM ocop_applications a JOIN ocop_products p ON p.id=a.product_id WHERE p.ma_co_so=? LIMIT 1", (row["ma_co_so"],)):
        raise OcopError("Chủ thể đã có hồ sơ; không được thay đổi xã/phường quản lý.", 409)
    if _text(data, "ma_co_so", 10, default=row["ma_co_so"]) != row["ma_co_so"]:
        raise OcopError("Không được thay đổi mã cơ sở.")
    when = _now()
    con.execute("UPDATE DM_CoSo SET TenCoSo=?,LoaiCoSo=?,DiaChi=?,Ma_DonViHanhChinh=? WHERE Ma_CoSo=?", (values["name"], values["facility_type"], values["address"], unit, row["ma_co_so"]))
    con.execute("UPDATE ocop_entities SET representative_name=?,phone=?,email=?,tax_code=?,website=?,description=?,updated_at=? WHERE id=? AND updated_at=?", (values["representative_name"], values["phone"], values["email"], values["tax_code"], values["website"], values["description"], when, row["id"], row["updated_at"]))
    con.execute("UPDATE ocop_products SET ma_don_vi_hanh_chinh=?,updated_at=? WHERE ma_co_so=?", (unit, when, row["ma_co_so"]))
    _audit(con, session, "entity", row["id"], "edit", {"before": row, "after": values, "unit": unit}, when)
    return get_entity(con, session, row["id"])


@_mutation
def archive_entity(con, session, object_id, data):
    row = get_entity(con, session, object_id)
    _version(row, data)
    if row["archived_at"]:
        raise OcopError("Chủ thể đã được lưu trữ.", 409)
    _lock_check(con, ma_co_so=row["ma_co_so"], archive=True)
    if _one(con, "SELECT id FROM ocop_products WHERE ma_co_so=? AND status='active' LIMIT 1", (row["ma_co_so"],)):
        raise OcopError("Hãy lưu trữ các sản phẩm đang hoạt động của chủ thể trước.", 409)
    when = _now()
    con.execute("UPDATE ocop_entities SET archived_at=?,updated_at=? WHERE id=? AND updated_at=?", (when, when, row["id"], row["updated_at"]))
    _audit(con, session, "entity", row["id"], "archive", {"before": row}, when)
    return get_entity(con, session, row["id"])


def _active_entity_by_code(con, session, code):
    row = _one(con, "SELECT id FROM ocop_entities WHERE ma_co_so=?", (code,))
    if not row:
        raise OcopError("Không tìm thấy chủ thể.", 404)
    entity = get_entity(con, session, row["id"])
    if entity["archived_at"]:
        raise OcopError("Chủ thể đã được lưu trữ.", 409)
    _check_unit(con, session, entity["ma_don_vi_hanh_chinh"])
    return entity


def _product_values(con, session, data):
    entity = _active_entity_by_code(con, session, _text(data, "ma_co_so", 10, True))
    criteria_set = _criteria_set_by_id(con, session, _value(data, "criteria_set_id"), require_active=True)
    name = _text(data, "name", 255, True)
    description = _text(data, "description", 5000)
    # product_group stays compatible with the shared master table; the exact
    # legal sub-group is represented by criteria_set_id.
    return entity, criteria_set, name, criteria_set["product_group"], description


@_mutation
def create_product(con, session, data):
    entity, criteria_set, name, group, description = _product_values(con, session, data)
    code, when = "P" + secrets.token_hex(4).upper(), _now()
    con.execute("INSERT INTO DM_SanPham(Ma_SanPham,TenSanPham,NhomSanPham,DonViTinh,TrangThai) VALUES(?,?,?,?,TRUE)", (code, name, group, ""))
    cursor = con.execute("""INSERT INTO ocop_products(ma_san_pham,ma_co_so,ma_don_vi_hanh_chinh,ten_san_pham,product_group,description,current_star,status,created_by,created_at,updated_at,criteria_set_id)
        VALUES(?,?,?,?,?,?,NULL,'active',?,?,?,?)""", (code, entity["ma_co_so"], entity["ma_don_vi_hanh_chinh"], name, group, description, session["user_id"], when, when, criteria_set["id"]))
    object_id = cursor.lastrowid
    _audit(con, session, "product", object_id, "create", {"code": code, "name": name, "group": group, "entity_id": entity["id"], "criteria_set_id": criteria_set["id"], "criteria_set_code": criteria_set["code"]}, when)
    return get_product(con, session, object_id)


@_mutation
def update_product(con, session, object_id, data):
    row = get_product(con, session, object_id)
    _version(row, data)
    if row["status"] != "active":
        raise OcopError("Sản phẩm đã được lưu trữ.", 409)
    _lock_check(con, product_id=row["id"])
    entity, criteria_set, name, group, description = _product_values(con, session, data)
    # Keep an existing application's jurisdiction stable even before submission.
    if entity["ma_co_so"] != row["ma_co_so"] and _one(con, "SELECT id FROM ocop_applications WHERE product_id=? LIMIT 1", (row["id"],)):
        raise OcopError("Sản phẩm đã có hồ sơ; không được thay đổi chủ thể.", 409)
    when = _now()
    con.execute("UPDATE DM_SanPham SET TenSanPham=?,NhomSanPham=? WHERE Ma_SanPham=?", (name, group, row["ma_san_pham"]))
    con.execute("UPDATE ocop_products SET ma_co_so=?,ma_don_vi_hanh_chinh=?,ten_san_pham=?,product_group=?,description=?,criteria_set_id=?,updated_at=? WHERE id=? AND updated_at=?", (entity["ma_co_so"], entity["ma_don_vi_hanh_chinh"], name, group, description, criteria_set["id"], when, row["id"], row["updated_at"]))
    # Drafts that have never been submitted follow the product's current set.
    # Returned/submitted history remains frozen to the set used on first submit.
    con.execute("""UPDATE ocop_applications SET criteria_set_id=?,updated_at=?,revision=revision+1
        WHERE product_id=? AND submitted_at IS NULL AND status='draft' AND criteria_set_id IS NOT ?""",
        (criteria_set["id"], when, row["id"], criteria_set["id"]))
    _audit(con, session, "product", row["id"], "edit", {"before": row, "after": {"name": name, "product_group": group, "description": description, "ma_co_so": entity["ma_co_so"], "criteria_set_id": criteria_set["id"], "criteria_set_code": criteria_set["code"]}}, when)
    return get_product(con, session, row["id"])


@_mutation
def archive_product(con, session, object_id, data):
    row = get_product(con, session, object_id)
    _version(row, data)
    if row["status"] != "active":
        raise OcopError("Sản phẩm đã được lưu trữ.", 409)
    _lock_check(con, product_id=row["id"], archive=True)
    when = _now()
    con.execute("UPDATE ocop_products SET status='archived',updated_at=? WHERE id=? AND updated_at=?", (when, row["id"], row["updated_at"]))
    con.execute("UPDATE DM_SanPham SET TrangThai=FALSE WHERE Ma_SanPham=?", (row["ma_san_pham"],))
    _audit(con, session, "product", row["id"], "archive", {"before": row}, when)
    return get_product(con, session, row["id"])


def _application_values(con, session, data, exclude_id=None):
    product = get_product(con, session, _number(_value(data, "product_id")))
    if product["status"] != "active" or product["entity_archived_at"]:
        raise OcopError("Chỉ lập hồ sơ cho sản phẩm và chủ thể đang hoạt động.", 409)
    _check_unit(con, session, product["ma_don_vi_hanh_chinh"])
    evaluation_type = _text(data, "evaluation_type", 30, True)
    if evaluation_type not in EVALUATION_TYPES:
        raise OcopError("Loại đăng ký đánh giá không hợp lệ.")
    year = _number(_value(data, "year"), 2000, 2100)
    sql = "SELECT id FROM ocop_applications WHERE product_id=? AND status IN (" + ",".join("?" for _ in OPEN_STATUSES) + ")"
    args = [product["id"], *OPEN_STATUSES]
    if exclude_id is not None:
        sql += " AND id<>?"
        args.append(exclude_id)
    if _one(con, sql + " LIMIT 1", args):
        raise OcopError("Sản phẩm đã có một hồ sơ đang xử lý.", 409)
    if not product.get("criteria_set_id"):
        raise OcopError("Sản phẩm chưa được gán bộ tiêu chí OCOP. Hãy cập nhật sản phẩm trước.", 409)
    criteria_set = _criteria_set_by_id(con, session, product["criteria_set_id"], require_active=True)
    return product, criteria_set, evaluation_type, year


@_mutation
def create_application(con, session, data):
    product, criteria_set, evaluation_type, year = _application_values(con, session, data)
    when = _now()
    cursor = con.execute("INSERT INTO ocop_applications(product_id,evaluation_type,year,status,created_by,created_at,updated_at,revision,criteria_set_id) VALUES(?,?,?,'draft',?,?,?,1,?)", (product["id"], evaluation_type, year, session["user_id"], when, when, criteria_set["id"]))
    object_id = cursor.lastrowid
    _review(con, session, object_id, "create", "Tạo hồ sơ nháp.", when)
    _audit(con, session, "application", object_id, "create", {"product_id": product["id"], "criteria_set_id": criteria_set["id"], "criteria_set_code": criteria_set["code"], "evaluation_type": evaluation_type, "year": year, "revision": 1}, when)
    return get_application(con, session, object_id)


@_mutation
def update_application(con, session, object_id, data):
    row = get_application(con, session, object_id)
    _version(row, data, "revision")
    if row["status"] not in ("draft", "returned"):
        raise OcopError("Chỉ sửa được hồ sơ nháp hoặc được trả lại.", 409)
    product, product_criteria, evaluation_type, year = _application_values(con, session, data, row["id"])
    if product["id"] != row["product_id"] and row["submitted_at"] is not None:
        raise OcopError("Hồ sơ đã từng gửi; không được thay đổi sản phẩm.", 409)
    criteria_set_id = row.get("criteria_set_id") if row["submitted_at"] is not None else product_criteria["id"]
    if not criteria_set_id:
        criteria_set_id = product_criteria["id"]
    when = _now()
    changed = con.execute("UPDATE ocop_applications SET product_id=?,criteria_set_id=?,evaluation_type=?,year=?,updated_at=?,revision=revision+1 WHERE id=? AND revision=?", (product["id"], criteria_set_id, evaluation_type, year, when, row["id"], row["revision"]))
    if changed.rowcount != 1:
        raise OcopError("Hồ sơ đã thay đổi. Vui lòng tải lại trang.", 409)
    _review(con, session, row["id"], "edit", "Cập nhật hồ sơ.", when)
    _audit(con, session, "application", row["id"], "edit", {"before": {k: row[k] for k in ("product_id", "criteria_set_id", "evaluation_type", "year", "revision")}, "after": {"product_id": product["id"], "criteria_set_id": criteria_set_id, "evaluation_type": evaluation_type, "year": year, "revision": row["revision"] + 1}}, when)
    return get_application(con, session, row["id"])


@_mutation
def application_action(con, session, object_id, action, data):
    row = get_application(con, session, object_id)
    _version(row, data, "revision")
    scope = get_scope(con, session)
    admin = scope is None
    transitions = {"submit": (("draft", "returned"), "submitted"), "start-review": (("submitted",), "checking"),
                   "return": (("submitted", "checking"), "returned"), "eligible": (("submitted", "checking"), "eligible"),
                   "cancel": (("draft", "returned", "submitted", "checking", "eligible") if admin else ("draft", "returned"), "cancelled")}
    if action not in transitions:
        raise OcopError("Thao tác hồ sơ không hợp lệ.")
    if action in ("start-review", "return", "eligible") and not admin:
        raise OcopError("Chỉ quản trị Chi cục có quyền kiểm tra hồ sơ.", 403)
    allowed, status = transitions[action]
    if row["status"] not in allowed:
        raise OcopError("Trạng thái hồ sơ hiện tại không cho phép thao tác này.", 409)
    comment = _text(data, "comment", 5000)
    if action == "return" and not comment:
        raise OcopError("Vui lòng ghi rõ nội dung cần bổ sung trước khi trả hồ sơ.")
    when = _now()
    fields = {"status": status, "updated_at": when, "revision": row["revision"] + 1}
    detail = {"from_status": row["status"], "to_status": status, "comment": comment, "revision": fields["revision"]}
    if action == "submit":
        product, product_criteria, _, _ = _application_values(con, session, row, row["id"])
        entity = get_entity(con, session, product["entity_id"])
        if row.get("submitted_at") is None:
            criteria_set = product_criteria
            fields["criteria_set_id"] = criteria_set["id"]
        else:
            if not row.get("criteria_set_id"):
                raise OcopError("Hồ sơ cũ chưa có bộ tiêu chí; cần cập nhật hồ sơ trước khi gửi lại.", 409)
            criteria_set = _criteria_set_by_id(con, session, row["criteria_set_id"], require_active=False)
        snapshot = {"schema_version": 2, "submitted_at": when, "application": {k: row[k] for k in ("id", "product_id", "evaluation_type", "year")}, "criteria_set": criteria_set, "product": product, "entity": entity, "revision": fields["revision"]}
        fields.update({"submitted_at": when, "reviewer_id": None, "checked_at": None, "reviewer_note": "", "submission_snapshot_json": json.dumps(snapshot, ensure_ascii=False, sort_keys=True, default=_json_value)})
        # Each submit's complete snapshot remains in the append-only audit history.
        detail["submission_snapshot"] = snapshot
    elif action in ("start-review", "return", "eligible"):
        fields.update({"checked_at": when, "reviewer_id": session["user_id"], "reviewer_note": comment})
    changed = con.execute("UPDATE ocop_applications SET " + ",".join(key + "=?" for key in fields) + " WHERE id=? AND revision=?", [*fields.values(), row["id"], row["revision"]])
    if changed.rowcount != 1:
        raise OcopError("Hồ sơ đã thay đổi. Vui lòng tải lại trang.", 409)
    _review(con, session, row["id"], action, comment, when)
    _audit(con, session, "application", row["id"], action, detail, when)
    return get_application(con, session, row["id"])
