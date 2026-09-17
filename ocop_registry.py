"""Shared OCOP registry writer for Excel and direct entry.

No staging or assessment application is manufactured here. The caller owns
the outer transaction; the savepoint also makes a rejected duplicate atomic.
"""
from copy import deepcopy
from datetime import date
import hashlib
import re
import unicodedata

import activity_log
import ocop_services as svc
from permissions import is_chi_cuc_user


class RegistryError(ValueError):
    status = 400


class DuplicateProduct(RegistryError):
    status = 409

    def __init__(self, products):
        super().__init__("Sản phẩm này đã tồn tại.")
        self.products = products


class AmbiguousEntity(RegistryError):
    status = 409

    def __init__(self, entities):
        super().__init__("Có nhiều chủ thể cùng tên tại địa bàn này. Vui lòng chọn chủ thể cần sử dụng.")
        self.entities = entities


BUSINESS_TYPES = ("Hộ", "Hợp tác xã", "Doanh nghiệp", "Tổ hợp tác")
MANUAL_ENTITY_CREATE = "ocop_manual_entity_create"
MANUAL_PRODUCT_CREATE = "ocop_manual_product_create"
MANUAL_RECOGNITION_CREATE = "ocop_manual_recognition_create"
MANUAL_UPDATE = "ocop_manual_update"


def text(value):
    return " ".join(unicodedata.normalize("NFC", str(value or "")).split())


def key(value):
    return text(value).casefold()


def source_key(*parts):
    return hashlib.sha256("\x1f".join(key(part) for part in parts).encode()).hexdigest()


def stable_code(prefix, identity):
    return prefix + hashlib.sha256(identity.encode()).hexdigest()[:8].upper()


def require_internal(con, session):
    if not is_chi_cuc_user(session):
        raise svc.OcopError("Chỉ tài khoản nội bộ Chi cục được nhập OCOP.", 403)
    svc.get_scope(con, session)  # Recheck active status and role in the database.


def group_options(con):
    return [row[0] for row in con.execute("""SELECT DISTINCT product_group FROM (
        SELECT product_group FROM app.ocop_criteria_sets WHERE active=TRUE
        UNION SELECT product_group FROM app.ocop_products WHERE status='active'
        ) groups WHERE product_group<>'' ORDER BY product_group""").fetchall()]


def _bounded(value, label, maximum=255, required=False):
    value = text(value)
    if (required and not value) or len(value) > maximum or "\x00" in value:
        raise RegistryError(f"{label}: vui lòng nhập nội dung hợp lệ (tối đa {maximum} ký tự).")
    return value


def _integer(value, label, minimum, maximum):
    if isinstance(value, bool) or not re.fullmatch(r"[0-9]{1,10}", str(value or "")):
        raise RegistryError(f"{label}: phải là số nguyên.")
    number = int(value)
    if not minimum <= number <= maximum:
        raise RegistryError(f"{label}: phải từ {minimum} đến {maximum}.")
    return number


def _date(value, label):
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value)).isoformat()
    except (ValueError, TypeError):
        raise RegistryError(f"{label}: ngày không hợp lệ.") from None


def validate_payload(payload, *, manual=False, append_existing=False):
    """Validate a canonical payload independently of its HTTP/Excel transport."""
    payload = deepcopy(payload)
    entity, product = payload["entity"], payload["product"]
    for field, label, limit, required in (
        ("name", "Tên chủ thể", 255, True), ("business_type", "Loại hình", 100, manual and not append_existing),
        ("address", "Địa chỉ", 255, False), ("representative_name", "Người đại diện", 255, False),
        ("phone", "Điện thoại", 50, False), ("email", "Email", 254, False),
    ):
        entity[field] = _bounded(entity.get(field), label, limit, required)
    if manual and not append_existing and entity["business_type"] not in BUSINESS_TYPES:
        raise RegistryError("Vui lòng chọn loại hình chủ thể trong danh sách.")
    if entity["email"] and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", entity["email"]):
        raise RegistryError("Email chủ thể không hợp lệ.")
    product["name"] = _bounded(product.get("name"), "Tên sản phẩm", 255, True)
    product["group"] = _bounded(product.get("group"), "Nhóm sản phẩm", 100, True)
    product["description"] = _bounded(product.get("description"), "Mô tả", 5000)
    recognitions = payload.get("recognitions")
    if not isinstance(recognitions, list) or not 1 <= len(recognitions) <= 50:
        raise RegistryError("Nhập từ 1 đến 50 lần công nhận trong một lần lưu.")
    seen = set()
    for row in recognitions:
        row["star_rank"] = _integer(row.get("star_rank"), "Hạng sao", 3, 5)
        row["recognition_year"] = _integer(row.get("recognition_year"), "Năm công nhận", 1900, 9999)
        if row.get("evaluation_type") not in svc.EVALUATION_TYPES:
            raise RegistryError("Loại đánh giá không hợp lệ.")
        row["recognition_date"] = _date(row.get("recognition_date"), "Ngày công nhận")
        row["expiry_date"] = _date(row.get("expiry_date"), "Ngày hết hạn")
        # Excel keeps its documented historical date/year warning; new manual
        # records must be consistent instead of creating more legacy anomalies.
        if manual and row["recognition_date"] and int(row["recognition_date"][:4]) != row["recognition_year"]:
            raise RegistryError("Năm của ngày công nhận phải khớp năm công nhận.")
        for field, label, limit in (("decision_number", "Số quyết định", 100),
                                    ("decision_authority", "Cơ quan ban hành", 255), ("note", "Ghi chú", 5000)):
            row[field] = _bounded(row.get(field), label, limit)
        signature = recognition_identity(row)
        if signature in seen:
            raise RegistryError("Một lần công nhận bị nhập trùng trong biểu mẫu.")
        seen.add(signature)
    return payload


def recognition_identity(row):
    return tuple(str(row.get(field) or "") for field in (
        "star_rank", "evaluation_type", "recognition_year", "recognition_date",
        "decision_number", "decision_authority", "expiry_date"))


def _resolve_entity(con, entity, selected_id=None):
    candidates = [dict(row) for row in con.execute("""SELECT e.*,c.TenCoSo AS name,
        c.LoaiCoSo AS business_type,c.DiaChi AS address,c.Ma_DonViHanhChinh AS unit_code
        FROM app.ocop_entities e JOIN DM_CoSo c ON c.Ma_CoSo=e.ma_co_so
        WHERE c.Ma_DonViHanhChinh=? ORDER BY e.id""", (entity["unit_code"],)).fetchall()
        if key(row["name"]) == key(entity["name"])]
    if selected_id:
        candidates = [row for row in candidates if str(row["id"]) == str(selected_id)]
        if not candidates:
            raise RegistryError("Chủ thể được chọn không khớp tên và địa bàn.")
    if len(candidates) > 1:
        raise AmbiguousEntity(candidates)
    if candidates:
        if candidates[0]["archived_at"]:
            raise RegistryError("Chủ thể đã ngưng sử dụng; cần kiểm tra lại trước khi nhập.")
        return candidates[0]
    return None


def _ensure_entity(con, session, entity, existing, source):
    now = svc._now()
    if existing:
        entity.update(ma_co_so=existing["ma_co_so"], name=existing["name"])
        if source == "excel":
            con.execute("""UPDATE DM_CoSo SET
                LoaiCoSo=CASE WHEN ?<>'' THEN ? ELSE LoaiCoSo END,
                DiaChi=CASE WHEN ?<>'' THEN ? ELSE DiaChi END WHERE Ma_CoSo=?""",
                (entity["business_type"], entity["business_type"], entity["address"], entity["address"], entity["ma_co_so"]))
            con.execute("""UPDATE app.ocop_entities SET
                representative_name=CASE WHEN ?<>'' THEN ? ELSE representative_name END,
                phone=CASE WHEN ?<>'' THEN ? ELSE phone END,updated_at=? WHERE id=?""",
                (entity["representative_name"], entity["representative_name"], entity["phone"], entity["phone"], now, existing["id"]))
        # Reusing a subject is not permission to silently replace its contacts.
        return existing["id"]
    code = entity["ma_co_so"]
    occupied = con.execute("SELECT TenCoSo,Ma_DonViHanhChinh FROM DM_CoSo WHERE Ma_CoSo=?", (code,)).fetchone()
    if occupied and (key(occupied[0]) != key(entity["name"]) or occupied[1] != entity["unit_code"]):
        raise RegistryError("Xung đột mã cơ sở tự sinh. Vui lòng kiểm tra chủ thể.")
    if not occupied:
        con.execute("INSERT INTO DM_CoSo(Ma_CoSo,TenCoSo,LoaiCoSo,DiaChi,Ma_DonViHanhChinh) VALUES(?,?,?,?,?)",
                    (code, entity["name"], entity["business_type"], entity["address"], entity["unit_code"]))
    return con.execute("""INSERT INTO app.ocop_entities
        (ma_co_so,representative_name,phone,email,tax_code,website,description,created_by,created_at,updated_at,source_key)
        VALUES(?,?,?,?,'','',?,?,?,?,?)""",
        (code, entity["representative_name"], entity["phone"], entity["email"],
         "Nhập trực tiếp" if source == "manual" else "Import dữ liệu OCOP lịch sử",
         session["user_id"], now, now, entity["source_key"])).lastrowid


def _ensure_product(con, session, entity, product, existing, source):
    now = svc._now()
    if existing:
        product.update(ma_san_pham=existing["ma_san_pham"], name=existing["ten_san_pham"])
        if source == "excel":
            con.execute("UPDATE DM_SanPham SET NhomSanPham=? WHERE Ma_SanPham=?", (product["group"], product["ma_san_pham"]))
            con.execute("UPDATE app.ocop_products SET product_group=?,updated_at=? WHERE id=?", (product["group"], now, existing["id"]))
        return existing["id"]
    if con.execute("SELECT 1 FROM DM_SanPham WHERE Ma_SanPham=?", (product["ma_san_pham"],)).fetchone():
        raise RegistryError("Xung đột mã sản phẩm tự sinh. Vui lòng kiểm tra sản phẩm.")
    con.execute("INSERT INTO DM_SanPham(Ma_SanPham,TenSanPham,NhomSanPham,DonViTinh,TrangThai) VALUES(?,?,?,NULL,TRUE)",
                (product["ma_san_pham"], product["name"], product["group"]))
    return con.execute("""INSERT INTO app.ocop_products
        (ma_san_pham,ma_co_so,ma_don_vi_hanh_chinh,ten_san_pham,product_group,description,current_star,status,
         created_by,created_at,updated_at,source_key)
        VALUES(?,?,?,?,?,?,NULL,'active',?,?,?,?)""",
        (product["ma_san_pham"], entity["ma_co_so"], entity["unit_code"], product["name"], product["group"],
         product["description"], session["user_id"], now, now, product["source_key"])).lastrowid


def _audit(con, session, action, detail, kind, object_id, metadata=None):
    # Old import regression fixtures represent pre-020 installations. Keep the
    # old audit contract there, and use full snapshots on the deployed schema.
    modern = con.execute("""SELECT 1 FROM information_schema.columns WHERE
        table_schema='app' AND table_name='audit_logs' AND column_name='username_snapshot'""").fetchone()
    if modern:
        activity_log.write_activity(con, session["user_id"], action, detail, module="ocop",
            object_type=kind, object_id=object_id, success=True, **(metadata or {}))
    else:
        con.execute("""INSERT INTO app.audit_logs(user_id,action,detail,created_at,module,object_type,object_id)
            VALUES(?,?,?,?,'ocop',?,?)""", (session["user_id"], action, detail, svc._now(), kind, str(object_id)))


def _upsert_recognitions(con, product_id, product, recognitions, batch_id=None, source_row=None, *, source="excel"):
    old = [dict(row) for row in con.execute("SELECT * FROM app.ocop_recognitions WHERE product_id=? ORDER BY recognition_sequence", (product_id,)).fetchall()]
    sequence = max((row["recognition_sequence"] for row in old), default=0)
    added = []
    for row in sorted(recognitions, key=lambda r: (int(r["recognition_year"]), str(r.get("recognition_date") or ""))):
        identity = recognition_identity(row)
        same_source = next((r for r in old if r["source_key"] == row.get("source_key")), None)
        same_facts = next((r for r in old if recognition_identity(r) == identity), None)
        if source == "manual" and same_facts:
            raise RegistryError("Lần công nhận này đã tồn tại; chưa lưu thêm dữ liệu.")
        if same_facts and not same_source:
            continue  # Cross-source duplicate: retain its original provenance.
        if same_source:
            con.execute("""UPDATE app.ocop_recognitions SET evaluation_type=?,star_rank=?,recognition_date=?,
                recognition_year=?,decision_number=?,decision_authority=?,expiry_date=?,note=?,
                source_batch_id=?,source_row=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                (row["evaluation_type"], row["star_rank"], row["recognition_date"], row["recognition_year"],
                 row["decision_number"], row["decision_authority"], row["expiry_date"], row["note"], batch_id, source_row, same_source["id"]))
        else:
            sequence += 1
            source_identity = row.get("source_key") if source == "excel" else source_key("manual", product["ma_san_pham"], *identity)
            new_id = con.execute("""INSERT INTO app.ocop_recognitions
                (product_id,application_id,source_key,recognition_sequence,evaluation_type,star_rank,
                 recognition_date,recognition_year,decision_number,decision_authority,expiry_date,is_current,note,source_batch_id,source_row)
                VALUES(?,NULL,?,?,?,?,?,?,?,?,?,FALSE,?,?,?) RETURNING id""",
                (product_id, source_identity, sequence, row["evaluation_type"], row["star_rank"], row["recognition_date"],
                 row["recognition_year"], row["decision_number"], row["decision_authority"], row["expiry_date"],
                 row["note"], batch_id, source_row)).fetchone()[0]
            added.append((new_id, row))
    current = con.execute("""SELECT id,star_rank FROM app.ocop_recognitions WHERE product_id=?
        ORDER BY recognition_year DESC,COALESCE(recognition_date,make_date(recognition_year,1,1)) DESC,
                 recognition_sequence DESC,id DESC LIMIT 1""", (product_id,)).fetchone()
    if current is None:
        raise RegistryError("Sản phẩm chưa có lần công nhận hợp lệ.")
    con.execute("UPDATE app.ocop_recognitions SET is_current=FALSE WHERE product_id=? AND is_current=TRUE", (product_id,))
    con.execute("UPDATE app.ocop_recognitions SET is_current=TRUE,updated_at=CURRENT_TIMESTAMP WHERE id=?", (current[0],))
    con.execute("UPDATE app.ocop_products SET current_star=?,updated_at=? WHERE id=?", (current[1], svc._now(), product_id))
    return current[0], added


def _publish_qd5277(con, entity, product, current_recognition_id):
    recognition = con.execute("SELECT * FROM app.ocop_recognitions WHERE id=?", (current_recognition_id,)).fetchone()
    year_code = str(recognition["recognition_year"])
    con.execute("""INSERT INTO DM_KhoangThoiGian(Ma_ThoiGian,Nam,Thang,VuMua)
        VALUES(?,?,NULL,NULL) ON CONFLICT(Ma_ThoiGian) DO NOTHING""", (year_code, recognition["recognition_year"]))
    expiry = recognition["expiry_date"]
    status = "HETHAN" if expiry and expiry < date.today() else "HIEULUC"
    if int(current_recognition_id) > 2147483647:
        raise RegistryError("Mã lịch sử công nhận vượt phạm vi MA_OCOP INT của QĐ 5277.")
    # PTNT_OCOP is the existing current-only projection; history stays untouched
    # in app.ocop_recognitions, including all prior Excel/manual source rows.
    con.execute("DELETE FROM PTNT_OCOP WHERE Ma_SanPham=? AND MA_OCOP<>?", (product["ma_san_pham"], int(current_recognition_id)))
    con.execute("""INSERT INTO PTNT_OCOP
        (MA_OCOP,Ma_DonViHanhChinh,Ma_ThoiGian,Ma_SanPham,TenSanPham,XepHang,ChuTheSXKD,DoanhThuNam,TrangThai)
        VALUES(?,?,?,?,?,?,?,NULL,?) ON CONFLICT(MA_OCOP) DO UPDATE SET
        Ma_DonViHanhChinh=excluded.Ma_DonViHanhChinh,Ma_ThoiGian=excluded.Ma_ThoiGian,
        Ma_SanPham=excluded.Ma_SanPham,TenSanPham=excluded.TenSanPham,XepHang=excluded.XepHang,
        ChuTheSXKD=excluded.ChuTheSXKD,TrangThai=excluded.TrangThai""",
        (int(current_recognition_id), entity["unit_code"], year_code, product["ma_san_pham"], product["name"],
         f"{recognition['star_rank']}*", entity["name"], status))


def publish(con, session, payload, *, source="excel", batch_id=None, source_row=None,
            append_product_id=None, selected_entity_id=None, metadata=None):
    with svc._transaction(con):
        if source not in ("excel", "manual"):
            raise RegistryError("Nguồn dữ liệu OCOP không hợp lệ.")
        require_internal(con, session)
        payload = validate_payload(payload, manual=source == "manual", append_existing=bool(append_product_id))
        entity, product = payload["entity"], payload["product"]
        unit = con.execute("""SELECT TenDonVi,TinhTrang,CapHanhChinh FROM DM_DonViHanhChinh
            WHERE Ma_DonViHanhChinh=? FOR SHARE""", (entity["unit_code"],)).fetchone()
        if not unit or not unit[1] or unit[2] not in ("xa", "phuong") or str(entity["unit_code"]).upper().startswith("TMP"):
            raise RegistryError("Vui lòng chọn xã/phường đang hoạt động trong danh mục.")
        if entity.get("unit_name") and entity["unit_name"] != unit[0]:
            raise RegistryError("Danh mục hành chính đã thay đổi. Vui lòng kiểm tra lại.")
        # Both transports serialize resolution and allocation within a locality.
        con.execute("SELECT pg_advisory_xact_lock(hashtext(?))", ("ocop_registry:" + entity["unit_code"],))
        existing_entity = _resolve_entity(con, entity, selected_entity_id)
        products = []
        if existing_entity:
            products = [dict(row) for row in con.execute("""SELECT * FROM app.ocop_products
                WHERE ma_co_so=? AND ma_don_vi_hanh_chinh=? ORDER BY id FOR UPDATE""",
                (existing_entity["ma_co_so"], entity["unit_code"])).fetchall() if key(row["ten_san_pham"]) == key(product["name"])]
        if append_product_id:
            products = [row for row in products if str(row["id"]) == str(append_product_id)]
            if not products:
                raise RegistryError("Sản phẩm được chọn không khớp chủ thể, địa bàn và tên sản phẩm.")
        elif source == "manual" and products:
            raise DuplicateProduct(products)
        if len(products) > 1:
            raise DuplicateProduct(products)
        existing_product = products[0] if products else None
        if existing_product and existing_product["status"] != "active":
            raise RegistryError("Sản phẩm đã ngưng sử dụng; chưa thể thêm công nhận.")
        if source == "manual" and not existing_product and product["group"] not in group_options(con):
            raise RegistryError("Nhóm sản phẩm không nằm trong danh mục hiện tại.")
        entity_id = _ensure_entity(con, session, entity, existing_entity, source)
        product_id = _ensure_product(con, session, entity, product, existing_product, source)
        current, added = _upsert_recognitions(con, product_id, product, payload["recognitions"], batch_id, source_row, source=source)
        _publish_qd5277(con, entity, product, current)
        if source == "manual":
            if not existing_entity:
                _audit(con, session, MANUAL_ENTITY_CREATE, f"Tạo chủ thể OCOP trực tiếp (mã {entity['ma_co_so']})", "entity", entity_id, metadata)
            if not existing_product:
                _audit(con, session, MANUAL_PRODUCT_CREATE, f"Tạo sản phẩm OCOP trực tiếp (mã {product['ma_san_pham']})", "product", product_id, metadata)
            for recognition_id, row in added:
                _audit(con, session, MANUAL_RECOGNITION_CREATE,
                       f"Thêm lần công nhận {row['star_rank']} sao năm {row['recognition_year']} (sản phẩm {product['ma_san_pham']})", "recognition", recognition_id, metadata)
            if existing_product:
                _audit(con, session, MANUAL_UPDATE, "Bổ sung lịch sử công nhận OCOP", "product", product_id, metadata)
        return {"product_id": product_id, "entity_id": entity_id, "current_recognition_id": current}


def record_failure(con, session):
    """Called only after rollback; do not copy rejected input or exception text."""
    try:
        activity_log.write_activity(con, session["user_id"], MANUAL_UPDATE,
            "Chưa lưu dữ liệu OCOP trực tiếp; kiểm tra lại biểu mẫu hoặc thử lại.", module="ocop", success=False)
        con.commit()
    except Exception:
        con.rollback()
