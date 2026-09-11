"""Shared administrative catalog. Caller owns transactions; no static unit list."""
from datetime import datetime
import json
import re
import unicodedata

from permissions import is_admin

LEVELS = {"tinh":"Tỉnh / Thành phố", "huyen":"Huyện / Quận", "xa":"Xã", "phuong":"Phường", "thitran":"Thị trấn"}
SELECT = """SELECT Ma_DonViHanhChinh AS code,TenDonVi AS name,CapHanhChinh AS level,
    Ma_DonViCapTren AS parent_code,TinhTrang AS active FROM DM_DonViHanhChinh"""


class CatalogError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def normalize(value):
    return " ".join(unicodedata.normalize("NFC", str(value or "")).split()).casefold()


def units(con, *, active_only=False, communes_only=False):
    conditions = ["upper(Ma_DonViHanhChinh) NOT LIKE 'TMP%'"]
    if active_only:
        conditions.append("TinhTrang=TRUE")
    if communes_only:
        conditions.append("CapHanhChinh IN ('xa','phuong')")
    return [dict(row) for row in con.execute(SELECT + " WHERE " + " AND ".join(conditions)
                                            + " ORDER BY TenDonVi,Ma_DonViHanhChinh").fetchall()]


def get_unit(con, code, *, lock=False):
    # SQLite writes hold BEGIN IMMEDIATE; PG must also keep the checked catalog
    # row stable until the account/import transaction commits.
    suffix = " FOR SHARE" if lock and hasattr(con, "_connection") else ""
    row = con.execute(SELECT + " WHERE Ma_DonViHanhChinh=?" + suffix, (code,)).fetchone()
    return dict(row) if row else None


def unit_lookup(con, *, active_only=True):
    """A per-request lookup; adding a DB row is immediately visible next request."""
    catalog = {row["code"]:row for row in units(con, active_only=active_only, communes_only=True)}
    names = {}
    for row in catalog.values():
        names.setdefault(normalize(row["name"]), set()).add(row["code"])
    for row in con.execute("SELECT alias,unit_code FROM admin_unit_aliases").fetchall():
        if row["unit_code"] in catalog:
            names.setdefault(normalize(row["alias"]), set()).add(row["unit_code"])

    def lookup(name):
        codes = names.get(normalize(name), set())
        if len(codes) != 1:
            return None
        row = catalog[next(iter(codes))]
        return row["name"], row["code"]
    return lookup


def require_admin(con, session):
    row = con.execute("SELECT role,active FROM users WHERE id=?", (session.get("user_id"),)).fetchone()
    if not is_admin(session) or not row or not row["active"] or row["role"] != "admin":
        raise CatalogError("Chỉ quản trị viên được quản lý danh mục hành chính.", 403)


def report_names(con, name):
    """Names stored by old reports remain attached to the same catalog code."""
    unit = unit_lookup(con, active_only=False)(name)
    if unit is None:
        return [name]
    aliases = [row[0] for row in con.execute("SELECT alias FROM admin_unit_aliases WHERE unit_code=?", (unit[1],)).fetchall()]
    return sorted(set([name, unit[0], *aliases]))


def audit(con, actor_id, action, code, before, after):
    detail = json.dumps({"code":code, "before":before, "after":after}, ensure_ascii=False, default=str)
    con.execute("""INSERT INTO audit_logs(record_id,user_id,action,detail,created_at)
        VALUES(NULL,?,?,?,?)""", (actor_id, action, detail, datetime.now().isoformat(timespec="seconds")))


def save_unit(con, session, data, code=None):
    if hasattr(con, "_connection"):
        con.execute("LOCK TABLE DM_DonViHanhChinh IN SHARE ROW EXCLUSIVE MODE")
    require_admin(con, session)
    old = get_unit(con, code) if code else None
    if code and not old:
        raise CatalogError("Không tìm thấy đơn vị.", 404)
    proposed_code = str(data.get("code", "")).strip()
    if code and proposed_code and proposed_code != code:
        raise CatalogError("Mã đơn vị đã tạo không được đổi; các dữ liệu liên kết dùng mã này.")
    code = code or proposed_code
    if not re.fullmatch(r"[0-9]{1,10}", code):
        raise CatalogError("Mã hành chính phải gồm 1–10 chữ số, không dùng mã TMP.")
    if old is None and get_unit(con, code):
        raise CatalogError("Mã đơn vị đã tồn tại.", 409)
    name = unicodedata.normalize("NFC", str(data.get("name", "")).strip())
    level = str(data.get("level", ""))
    parent = str(data.get("parent_code", "")).strip() or None
    active = data.get("active") in (True, "1", "true")
    if not name or len(name) > 255 or level not in LEVELS:
        raise CatalogError("Nhập tên đơn vị (tối đa 255 ký tự) và cấp hành chính hợp lệ.")
    # Name-based Excel lookup must remain unambiguous, including previous names.
    candidates = [(u["name"],u["code"]) for u in units(con)]
    candidates += [(r[0],r[1]) for r in con.execute("SELECT alias,unit_code FROM admin_unit_aliases").fetchall()]
    if any(normalize(n) == normalize(name) and c != code for n,c in candidates):
        raise CatalogError("Tên đơn vị trùng tên hoặc tên cũ của một mã khác.", 409)
    seen = {code}
    cursor = parent
    while cursor:
        if cursor in seen:
            raise CatalogError("Đơn vị cấp trên không được tạo vòng lặp.")
        seen.add(cursor)
        ancestor = get_unit(con, cursor)
        if not ancestor:
            raise CatalogError("Mã đơn vị cấp trên không tồn tại.")
        cursor = ancestor["parent_code"]
    if old is None:
        con.execute("""INSERT INTO DM_DonViHanhChinh
            (Ma_DonViHanhChinh,TenDonVi,CapHanhChinh,Ma_DonViCapTren,TinhTrang) VALUES(?,?,?,?,?)""",
            (code,name,level,parent,active))
    else:
        if old["name"] != name:
            # Keep historical report names resolvable, without rewriting raw reports.
            con.execute("INSERT INTO admin_unit_aliases(alias,unit_code) VALUES(?,?) ON CONFLICT(alias) DO NOTHING", (old["name"],code))
        con.execute("""UPDATE DM_DonViHanhChinh SET TenDonVi=?,CapHanhChinh=?,Ma_DonViCapTren=?,TinhTrang=?
            WHERE Ma_DonViHanhChinh=?""", (name,level,parent,active,code))
        con.execute("""UPDATE users SET unit_name=? WHERE role='unit' AND id IN
            (SELECT user_id FROM user_admin_units WHERE ma_don_vi_hanh_chinh=?)""", (name,code))
    audit(con, session["user_id"], "Sửa đơn vị hành chính" if old else "Thêm đơn vị hành chính", code, old, get_unit(con,code))
    return code


def set_active(con, session, code, active):
    require_admin(con, session)
    old = get_unit(con,code)
    if not old:
        raise CatalogError("Không tìm thấy đơn vị.", 404)
    con.execute("UPDATE DM_DonViHanhChinh SET TinhTrang=? WHERE Ma_DonViHanhChinh=?", (bool(active),code))
    audit(con,session["user_id"],"Kích hoạt đơn vị" if active else "Ngưng đơn vị",code,old,get_unit(con,code))


def account_unit(con, role, data):
    if role != "unit":
        return str(data.get("unit_name", "")).strip() or "Chi cục", None
    row = get_unit(con,str(data.get("unit_code", "")).strip(), lock=True)
    if not row or not row["active"] or row["level"] not in ("xa","phuong") or row["code"].upper().startswith("TMP"):
        raise CatalogError("Chọn xã/phường đang hoạt động từ danh mục hành chính.")
    return row["name"], row["code"]


def assign_account(con, actor_id, user_id, code):
    old = con.execute("SELECT ma_don_vi_hanh_chinh FROM user_admin_units WHERE user_id=?", (user_id,)).fetchone()
    # Retain an old assignment when promoting a user; role checks determine scope.
    if code is None:
        return
    con.execute("""INSERT INTO user_admin_units(user_id,ma_don_vi_hanh_chinh) VALUES(?,?)
        ON CONFLICT(user_id) DO UPDATE SET ma_don_vi_hanh_chinh=excluded.ma_don_vi_hanh_chinh""", (user_id,code))
    con.execute("UPDATE users SET unit_name=(SELECT TenDonVi FROM DM_DonViHanhChinh WHERE Ma_DonViHanhChinh=?) WHERE id=?", (code,user_id))
    if old is None or old[0] != code:
        audit(con,actor_id,"Đổi địa bàn tài khoản",str(user_id),old[0] if old else None,code)


def validate_weekly_units(con, preview):
    """Revalidate catalog membership at confirmation; leave import calculations intact."""
    for row in preview["rows"]:
        data = row["canonical"]
        unit = get_unit(con,data.get("ma_don_vi_hanh_chinh"), lock=True)
        if not unit or not unit["active"] or unit["level"] not in ("xa","phuong") or unit["name"] != data.get("unit_name"):
            raise CatalogError("Danh mục hành chính đã thay đổi. Hãy tải lại file để kiểm tra.")
