"""Safe import of the historical OCOP workbook into PostgreSQL.

The source workbook is preserved row-by-row in staging before normalized data
is published. Unknown administrative units are never invented: they remain
visible as validation errors until the shared administrative catalog maps them.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
import hashlib
import io
import json
import re
import unicodedata

from permissions import is_chi_cuc_user


class OcopImportError(ValueError):
    pass


DEFAULT_SHEET = "Loc"
MAX_FILE_BYTES = 20 * 1024 * 1024


def _text(value) -> str:
    if value is None:
        return ""
    return " ".join(unicodedata.normalize("NFC", str(value)).split()).strip()


def _key(value) -> str:
    return _text(value).casefold()


def _json_value(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _star(value, label: str, errors: list[str], *, required=True):
    if value in (None, ""):
        if required:
            errors.append(f"{label}: thiếu hạng sao.")
        return None
    try:
        star = int(float(str(value).strip()))
    except (TypeError, ValueError):
        errors.append(f"{label}: hạng sao không hợp lệ ({value!r}).")
        return None
    if star not in (3, 4, 5):
        errors.append(f"{label}: hạng sao phải là 3, 4 hoặc 5.")
        return None
    return star


def _year(value, label: str, errors: list[str], *, required=True):
    if value in (None, ""):
        if required:
            errors.append(f"{label}: thiếu năm công nhận.")
        return None
    try:
        year = int(float(str(value).strip()))
    except (TypeError, ValueError):
        errors.append(f"{label}: năm không hợp lệ ({value!r}).")
        return None
    if not 1900 <= year <= 9999:
        errors.append(f"{label}: năm nằm ngoài phạm vi hợp lệ.")
        return None
    return year


def _date_value(value, label: str, errors: list[str], *, required=False):
    if value in (None, ""):
        if required:
            errors.append(f"{label}: thiếu ngày.")
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        try:
            return date(1899, 12, 30) + timedelta(days=float(value))
        except (OverflowError, ValueError):
            errors.append(f"{label}: ngày Excel không hợp lệ ({value!r}).")
            return None
    token = _text(value)
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(token, fmt).date()
        except ValueError:
            pass
    errors.append(f"{label}: ngày không hợp lệ ({value!r}).")
    return None


def _stable_code(prefix: str, natural_key: str) -> str:
    return prefix + hashlib.sha256(natural_key.encode("utf-8")).hexdigest()[:8].upper()


def _source_key(*parts) -> str:
    token = "\x1f".join(_key(part) for part in parts)
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _lookup_unit(source_name: str, unit_lookup):
    raw = _text(source_name)
    if not raw:
        return None, []
    candidates = [raw]
    folded = raw.casefold()
    if not folded.startswith(("xã ", "phường ", "thị trấn ")):
        candidates.extend((f"Xã {raw}", f"Phường {raw}", f"Thị trấn {raw}"))
    matches = {}
    for candidate in candidates:
        result = unit_lookup(candidate)
        if result:
            name, code = result
            matches[str(code)] = (name, str(code))
    if len(matches) == 1:
        return next(iter(matches.values())), []
    if len(matches) > 1:
        return None, [f"Địa bàn '{raw}' khớp nhiều mã hành chính; cần bổ sung alias rõ ràng."]
    return None, [f"Địa bàn chưa có mã trong danh mục hành chính: {raw}."]


def parse_ocop_workbook(file_bytes: bytes, filename: str, unit_lookup, sheet_name: str = DEFAULT_SHEET):
    """Parse the legacy OCOP workbook into a serializable preview.

    Entity-level cells that are visually merged/continued are inherited only
    when the subject is the same as the preceding product (or the subject cell
    itself is blank). This prevents accidentally carrying metadata to a new
    subject that merely has a blank optional field.
    """
    if not file_bytes:
        raise OcopImportError("File Excel rỗng.")
    if len(file_bytes) > MAX_FILE_BYTES:
        raise OcopImportError("File Excel quá lớn (tối đa 20 MB).")
    if not str(filename or "").lower().endswith(".xlsx"):
        raise OcopImportError("Chỉ hỗ trợ file .xlsx.")
    try:
        from openpyxl import load_workbook
    except Exception as exc:
        raise OcopImportError("Máy chủ chưa cài openpyxl.") from exc
    try:
        raw_book = load_workbook(io.BytesIO(file_bytes), data_only=False, read_only=True)
        value_book = load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
    except Exception as exc:
        raise OcopImportError(f"Không đọc được file Excel: {exc}") from exc

    try:
        selected = _text(sheet_name) or DEFAULT_SHEET
        if selected not in value_book.sheetnames:
            raise OcopImportError(
                f"Không tìm thấy sheet '{selected}'. Có: {', '.join(value_book.sheetnames)}"
            )
        raw_sheet = raw_book[selected]
        sheet = value_book[selected]
        rows = []
        entity_context = None
        source_units = set()
        mapped_units = set()
        entity_keys = set()
        product_keys = set()

        raw_rows = raw_sheet.iter_rows(min_row=5, max_col=22, values_only=True)
        value_rows = sheet.iter_rows(min_row=5, max_col=22, values_only=True)
        for excel_row, (raw_values, values) in enumerate(zip(raw_rows, value_rows), 5):
            values = list(values)
            product_name = _text(values[1])
            source_tt = _text(values[0])
            if not product_name:
                continue
            # Summary/footer rows do not carry a product sequence number.
            if not source_tt or not re.fullmatch(r"\d+(?:\.0+)?", source_tt):
                continue

            errors: list[str] = []
            warnings: list[str] = []
            entity_name_raw = _text(values[4])
            current_same_entity = bool(
                entity_context and entity_name_raw and _key(entity_name_raw) == _key(entity_context["entity_name"])
            )
            if entity_name_raw:
                if current_same_entity:
                    context = dict(entity_context)
                    for key, index in (
                        ("business_type", 3), ("entity_name", 4), ("source_unit_name", 5),
                        ("address", 6), ("representative_name", 7), ("phone", 8),
                    ):
                        incoming = _text(values[index])
                        if incoming:
                            context[key] = incoming
                    entity_context = context
                else:
                    entity_context = {
                        "business_type": _text(values[3]),
                        "entity_name": entity_name_raw,
                        "source_unit_name": _text(values[5]),
                        "address": _text(values[6]),
                        "representative_name": _text(values[7]),
                        "phone": _text(values[8]),
                    }
            elif entity_context:
                # A blank subject is the workbook's merged-cell continuation convention.
                entity_context = dict(entity_context)
            else:
                entity_context = {
                    "business_type": "", "entity_name": "", "source_unit_name": "",
                    "address": "", "representative_name": "", "phone": "",
                }
                errors.append("Không xác định được chủ thể cho dòng sản phẩm này.")

            context = dict(entity_context)
            entity_name = _text(context.get("entity_name"))
            source_unit_name = _text(context.get("source_unit_name"))
            product_group = _text(values[2])
            if not entity_name:
                errors.append("Thiếu tên chủ thể.")
            if not source_unit_name:
                errors.append("Thiếu xã/phường của chủ thể.")
            if not product_group:
                errors.append("Thiếu nhóm sản phẩm.")
            if not context.get("business_type"):
                warnings.append("Chủ thể chưa có loại hình kinh doanh trong file nguồn.")

            official, unit_messages = _lookup_unit(source_unit_name, unit_lookup)
            if unit_messages:
                errors.extend(unit_messages)
            if official:
                official_unit_name, unit_code = official
                mapped_units.add(unit_code)
            else:
                official_unit_name, unit_code = "", None
            if source_unit_name:
                source_units.add(source_unit_name)

            current_star = _star(values[9], "Hạng sao hiện tại", errors)
            expiry_date = _date_value(values[10], "Ngày hết hạn", errors)
            first_star = _star(values[11], "Đánh giá lần 1", errors)
            first_date = _date_value(values[12], "Ngày công nhận lần 1", errors)
            first_year = _year(values[13], "Năm công nhận lần 1", errors)
            first_decision = _text(values[14])
            first_authority = _text(values[15])
            if first_date and first_year and first_date.year != first_year:
                warnings.append(
                    f"Lần 1: ngày công nhận {first_date.isoformat()} không cùng năm với cột năm {first_year}; giữ nguyên cả hai giá trị nguồn."
                )

            second_present = any(values[i] not in (None, "") for i in range(16, 21))
            second_star = second_date = second_year = None
            second_decision = second_authority = ""
            if second_present:
                second_star = _star(values[16], "Đánh giá lần 2/nâng hạng", errors)
                second_date = _date_value(values[17], "Ngày công nhận lần 2", errors)
                second_year = _year(values[18], "Năm công nhận lần 2", errors)
                second_decision = _text(values[19])
                second_authority = _text(values[20])
                if second_date and second_year and second_date.year != second_year:
                    warnings.append(
                        f"Lần 2: ngày công nhận {second_date.isoformat()} không cùng năm với cột năm {second_year}; giữ nguyên cả hai giá trị nguồn."
                    )

            latest_star = second_star if second_present else first_star
            if current_star is not None and latest_star is not None and current_star != latest_star:
                errors.append(
                    f"Hạng sao hiện tại ({current_star}) khác lần công nhận gần nhất ({latest_star}); không tự sửa dữ liệu nguồn."
                )

            entity_natural = f"{_key(source_unit_name)}|{_key(entity_name)}"
            product_natural = f"{entity_natural}|{_key(product_name)}"
            entity_source_key = _source_key("entity", source_unit_name, entity_name)
            product_source_key = _source_key("product", source_unit_name, entity_name, product_name)
            ma_co_so = _stable_code("CS", entity_natural)
            ma_san_pham = _stable_code("OP", product_natural)
            if entity_natural in entity_keys and not current_same_entity and entity_name_raw:
                # Repeated subjects are valid; this message is informational only.
                pass
            entity_keys.add(entity_natural)
            if product_natural in product_keys:
                errors.append("Sản phẩm bị trùng cùng chủ thể và địa bàn trong file nguồn.")
            product_keys.add(product_natural)

            recognitions = []
            if first_star is not None and first_year is not None:
                recognitions.append({
                    "source_key": _source_key(product_source_key, "recognition", "1"),
                    "recognition_sequence": 1,
                    "evaluation_type": "new",
                    "star_rank": first_star,
                    "recognition_date": first_date.isoformat() if first_date else None,
                    "recognition_year": first_year,
                    "decision_number": first_decision,
                    "decision_authority": first_authority,
                    "expiry_date": expiry_date.isoformat() if (not second_present and expiry_date) else None,
                    "is_current": not second_present,
                    "note": _text(values[21]) if not second_present else "",
                })
            if second_present and second_star is not None and second_year is not None:
                evaluation_type = "upgrade" if first_star is not None and second_star > first_star else "re_evaluation"
                recognitions.append({
                    "source_key": _source_key(product_source_key, "recognition", "2"),
                    "recognition_sequence": 2,
                    "evaluation_type": evaluation_type,
                    "star_rank": second_star,
                    "recognition_date": second_date.isoformat() if second_date else None,
                    "recognition_year": second_year,
                    "decision_number": second_decision,
                    "decision_authority": second_authority,
                    "expiry_date": expiry_date.isoformat() if expiry_date else None,
                    "is_current": True,
                    "note": _text(values[21]),
                })

            canonical = {
                "source_tt": source_tt,
                "source_unit_name": source_unit_name,
                "entity": {
                    "source_key": entity_source_key,
                    "ma_co_so": ma_co_so,
                    "name": entity_name,
                    "business_type": _text(context.get("business_type")),
                    "unit_code": unit_code,
                    "unit_name": official_unit_name,
                    "address": _text(context.get("address")),
                    "representative_name": _text(context.get("representative_name")),
                    "phone": _text(context.get("phone")),
                },
                "product": {
                    "source_key": product_source_key,
                    "ma_san_pham": ma_san_pham,
                    "name": product_name,
                    "group": product_group,
                    "current_star": current_star,
                },
                "recognitions": recognitions,
            }
            raw_data = {
                chr(65 + i): {"raw": _json_value(raw_values[i]), "value": _json_value(values[i])}
                for i in range(22)
            }
            status = "error" if errors else ("warning" if warnings else "valid")
            rows.append({
                "excel_row": excel_row,
                "source_tt": source_tt,
                "source_unit_name": source_unit_name,
                "status": status,
                "errors": errors,
                "warnings": warnings,
                "raw_data": raw_data,
                "canonical": canonical,
            })

        if not rows:
            raise OcopImportError("Không tìm thấy dòng sản phẩm OCOP trong sheet đã chọn.")
        return {
            "filename": filename,
            "file_sha256": hashlib.sha256(file_bytes).hexdigest(),
            "sheet_name": selected,
            "rows": rows,
            "total_rows": len(rows),
            "valid_rows": sum(row["status"] == "valid" for row in rows),
            "warning_rows": sum(row["status"] == "warning" for row in rows),
            "error_rows": sum(row["status"] == "error" for row in rows),
            "source_unit_count": len(source_units),
            "mapped_unit_count": len(mapped_units),
            "unknown_units": sorted({row["source_unit_name"] for row in rows if not row["canonical"]["entity"]["unit_code"]}),
            "entity_count": len(entity_keys),
            "product_count": len(product_keys),
            "recognition_count": sum(len(row["canonical"]["recognitions"]) for row in rows),
        }
    finally:
        raw_book.close()
        value_book.close()


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _assert_publishable(preview):
    if preview.get("error_rows"):
        raise OcopImportError(
            f"Còn {preview['error_rows']} dòng lỗi. Chỉ có thể lưu staging; chưa thể đồng bộ OCOP chính thức."
        )


def _revalidate_unit(con, entity):
    row = con.execute(
        """SELECT Ma_DonViHanhChinh,TenDonVi,TinhTrang,CapHanhChinh
           FROM DM_DonViHanhChinh WHERE Ma_DonViHanhChinh=? FOR SHARE""",
        (entity["unit_code"],),
    ).fetchone()
    if (not row or not row["TinhTrang"] or row["CapHanhChinh"] not in ("xa", "phuong")
            or row["TenDonVi"] != entity["unit_name"]):
        raise OcopImportError("Danh mục hành chính đã thay đổi. Hãy tải lại file để kiểm tra.")


def _ensure_entity(con, session, entity):
    _revalidate_unit(con, entity)
    occupied = con.execute("SELECT TenCoSo,Ma_DonViHanhChinh FROM DM_CoSo WHERE Ma_CoSo=?", (entity["ma_co_so"],)).fetchone()
    if occupied and (occupied["TenCoSo"] != entity["name"] or occupied["Ma_DonViHanhChinh"] != entity["unit_code"]):
        raise OcopImportError(f"Xung đột mã chủ thể sinh tự động {entity['ma_co_so']}; dừng để kiểm tra.")
    con.execute(
        """INSERT INTO DM_CoSo(Ma_CoSo,TenCoSo,LoaiCoSo,DiaChi,Ma_DonViHanhChinh)
           VALUES(?,?,?,?,?)
           ON CONFLICT(Ma_CoSo) DO UPDATE SET
             TenCoSo=excluded.TenCoSo,
             LoaiCoSo=CASE WHEN excluded.LoaiCoSo<>'' THEN excluded.LoaiCoSo ELSE DM_CoSo.LoaiCoSo END,
             DiaChi=CASE WHEN excluded.DiaChi<>'' THEN excluded.DiaChi ELSE DM_CoSo.DiaChi END,
             Ma_DonViHanhChinh=excluded.Ma_DonViHanhChinh""",
        (entity["ma_co_so"], entity["name"], entity["business_type"], entity["address"], entity["unit_code"]),
    )
    existing = con.execute(
        "SELECT id,source_key FROM ocop_entities WHERE ma_co_so=? OR source_key=? ORDER BY id LIMIT 1",
        (entity["ma_co_so"], entity["source_key"]),
    ).fetchone()
    now = datetime.now().isoformat(timespec="seconds")
    if existing:
        con.execute(
            """UPDATE ocop_entities SET source_key=?,
                 representative_name=CASE WHEN ?<>'' THEN ? ELSE representative_name END,
                 phone=CASE WHEN ?<>'' THEN ? ELSE phone END,
                 updated_at=?
               WHERE id=?""",
            (entity["source_key"], entity["representative_name"], entity["representative_name"],
             entity["phone"], entity["phone"], now, existing["id"]),
        )
        return existing["id"]
    return con.execute(
        """INSERT INTO ocop_entities
           (ma_co_so,representative_name,phone,email,tax_code,website,description,created_by,created_at,updated_at,source_key)
           VALUES(?,?,?,'','','','Import dữ liệu OCOP lịch sử',?,?,?,?)""",
        (entity["ma_co_so"], entity["representative_name"], entity["phone"],
         session["user_id"], now, now, entity["source_key"]),
    ).lastrowid


def _ensure_product(con, session, entity, product):
    occupied = con.execute("SELECT TenSanPham FROM DM_SanPham WHERE Ma_SanPham=?", (product["ma_san_pham"],)).fetchone()
    if occupied and occupied["TenSanPham"] != product["name"]:
        raise OcopImportError(f"Xung đột mã sản phẩm sinh tự động {product['ma_san_pham']}; dừng để kiểm tra.")
    con.execute(
        """INSERT INTO DM_SanPham(Ma_SanPham,TenSanPham,NhomSanPham,DonViTinh,TrangThai)
           VALUES(?,?,?,NULL,TRUE)
           ON CONFLICT(Ma_SanPham) DO UPDATE SET
             TenSanPham=excluded.TenSanPham,NhomSanPham=excluded.NhomSanPham,TrangThai=TRUE""",
        (product["ma_san_pham"], product["name"], product["group"]),
    )
    existing = con.execute(
        "SELECT id FROM ocop_products WHERE ma_san_pham=? OR source_key=? ORDER BY id LIMIT 1",
        (product["ma_san_pham"], product["source_key"]),
    ).fetchone()
    now = datetime.now().isoformat(timespec="seconds")
    if existing:
        con.execute(
            """UPDATE ocop_products SET ma_co_so=?,ma_don_vi_hanh_chinh=?,ten_san_pham=?,product_group=?,
                 current_star=?,status='active',updated_at=?,source_key=? WHERE id=?""",
            (entity["ma_co_so"], entity["unit_code"], product["name"], product["group"],
             product["current_star"], now, product["source_key"], existing["id"]),
        )
        return existing["id"]
    return con.execute(
        """INSERT INTO ocop_products
           (ma_san_pham,ma_co_so,ma_don_vi_hanh_chinh,ten_san_pham,product_group,description,current_star,status,
            created_by,created_at,updated_at,source_key)
           VALUES(?,?,?,?,?,'Import dữ liệu OCOP lịch sử',?,'active',?,?,?,?)""",
        (product["ma_san_pham"], entity["ma_co_so"], entity["unit_code"], product["name"], product["group"],
         product["current_star"], session["user_id"], now, now, product["source_key"]),
    ).lastrowid


def _upsert_recognitions(con, product_id, product, recognitions, batch_id, source_row):
    con.execute("UPDATE ocop_recognitions SET is_current=FALSE,updated_at=CURRENT_TIMESTAMP WHERE product_id=?", (product_id,))
    current_id = None
    for recognition in recognitions:
        con.execute(
            """INSERT INTO ocop_recognitions
               (product_id,application_id,source_key,recognition_sequence,evaluation_type,star_rank,
                recognition_date,recognition_year,decision_number,decision_authority,expiry_date,is_current,note,
                source_batch_id,source_row,created_at,updated_at)
               VALUES(?,NULL,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
               ON CONFLICT(source_key) DO UPDATE SET
                 product_id=excluded.product_id,
                 recognition_sequence=excluded.recognition_sequence,
                 evaluation_type=excluded.evaluation_type,
                 star_rank=excluded.star_rank,
                 recognition_date=excluded.recognition_date,
                 recognition_year=excluded.recognition_year,
                 decision_number=excluded.decision_number,
                 decision_authority=excluded.decision_authority,
                 expiry_date=excluded.expiry_date,
                 is_current=excluded.is_current,
                 note=excluded.note,
                 source_batch_id=excluded.source_batch_id,
                 source_row=excluded.source_row,
                 updated_at=CURRENT_TIMESTAMP""",
            (product_id, recognition["source_key"], recognition["recognition_sequence"], recognition["evaluation_type"],
             recognition["star_rank"], recognition["recognition_date"], recognition["recognition_year"],
             recognition["decision_number"], recognition["decision_authority"], recognition["expiry_date"],
             bool(recognition["is_current"]), recognition["note"], batch_id, source_row),
        )
        row = con.execute("SELECT id FROM ocop_recognitions WHERE source_key=?", (recognition["source_key"],)).fetchone()
        if recognition["is_current"]:
            current_id = row["id"]
    if current_id is None:
        raise OcopImportError(f"Sản phẩm {product['name']} không có lần công nhận hiện hành hợp lệ.")
    return current_id


def _publish_qd5277(con, entity, product, current_recognition_id):
    recognition = con.execute("SELECT * FROM ocop_recognitions WHERE id=?", (current_recognition_id,)).fetchone()
    year_code = str(recognition["recognition_year"])
    con.execute(
        """INSERT INTO DM_KhoangThoiGian(Ma_ThoiGian,Nam,Thang,VuMua)
           VALUES(?,?,NULL,NULL) ON CONFLICT(Ma_ThoiGian) DO NOTHING""",
        (year_code, recognition["recognition_year"]),
    )
    expiry = recognition["expiry_date"]
    status = "HETHAN" if expiry and expiry < date.today() else "HIEULUC"
    if int(current_recognition_id) > 2147483647:
        raise OcopImportError("Mã lịch sử công nhận vượt phạm vi MA_OCOP INT của QĐ 5277.")
    con.execute("DELETE FROM PTNT_OCOP WHERE Ma_SanPham=? AND MA_OCOP<>?", (product["ma_san_pham"], int(current_recognition_id)))
    con.execute(
        """INSERT INTO PTNT_OCOP
           (MA_OCOP,Ma_DonViHanhChinh,Ma_ThoiGian,Ma_SanPham,TenSanPham,XepHang,ChuTheSXKD,DoanhThuNam,TrangThai)
           VALUES(?,?,?,?,?,?,?,NULL,?)
           ON CONFLICT(MA_OCOP) DO UPDATE SET
             Ma_DonViHanhChinh=excluded.Ma_DonViHanhChinh,
             Ma_ThoiGian=excluded.Ma_ThoiGian,
             Ma_SanPham=excluded.Ma_SanPham,
             TenSanPham=excluded.TenSanPham,
             XepHang=excluded.XepHang,
             ChuTheSXKD=excluded.ChuTheSXKD,
             TrangThai=excluded.TrangThai""",
        (int(current_recognition_id), entity["unit_code"], year_code, product["ma_san_pham"], product["name"],
         f"{recognition['star_rank']}*", entity["name"], status),
    )


def commit_ocop_preview(con, session, preview, mode="publish"):
    """Persist staging rows and optionally publish normalized OCOP history.

    ``stage_only`` is deliberately allowed when the workbook contains unknown
    administrative units. ``publish`` is all-or-nothing and requires zero errors.
    Caller owns commit/rollback.
    """
    if not is_chi_cuc_user(session):
        raise OcopImportError("Chỉ tài khoản Chi cục được import dữ liệu OCOP.")
    if mode not in ("stage_only", "publish"):
        raise OcopImportError("Chế độ import OCOP không hợp lệ.")
    if mode == "publish":
        _assert_publishable(preview)

    existing = con.execute(
        "SELECT * FROM ocop_import_batches WHERE file_sha256=? AND sheet_name=? FOR UPDATE",
        (preview["file_sha256"], preview["sheet_name"]),
    ).fetchone()
    if existing and existing["status"] == "published":
        return {"batch_id": existing["id"], "already_published": True, "published_products": 0}

    if existing:
        batch_id = existing["id"]
        con.execute("DELETE FROM ocop_import_rows WHERE batch_id=?", (batch_id,))
        con.execute(
            """UPDATE ocop_import_batches SET filename=?,total_rows=?,valid_rows=?,warning_rows=?,error_rows=?,
               commit_mode=?,status=?,imported_by=?,imported_at=CURRENT_TIMESTAMP,
               published_at=CASE WHEN ?='publish' THEN CURRENT_TIMESTAMP ELSE NULL END WHERE id=?""",
            (preview["filename"], preview["total_rows"], preview["valid_rows"], preview["warning_rows"],
             preview["error_rows"], mode, "published" if mode == "publish" else "committed", session["user_id"], mode, batch_id),
        )
    else:
        cursor = con.execute(
            """INSERT INTO ocop_import_batches
               (filename,file_sha256,sheet_name,total_rows,valid_rows,warning_rows,error_rows,commit_mode,status,imported_by,published_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,CASE WHEN ?='publish' THEN CURRENT_TIMESTAMP ELSE NULL END)
               RETURNING id""",
            (preview["filename"], preview["file_sha256"], preview["sheet_name"], preview["total_rows"],
             preview["valid_rows"], preview["warning_rows"], preview["error_rows"], mode,
             "published" if mode == "publish" else "committed", session["user_id"], mode),
        )
        batch_id = cursor.fetchone()[0]

    for row in preview["rows"]:
        messages = [{"level": "error", "message": item} for item in row["errors"]]
        messages += [{"level": "warning", "message": item} for item in row["warnings"]]
        con.execute(
            """INSERT INTO ocop_import_rows
               (batch_id,excel_row,source_tt,source_unit_name,mapped_unit_code,validation_status,
                validation_messages_json,raw_data_json,canonical_data_json)
               VALUES(?,?,?,?,?,?,CAST(? AS JSONB),CAST(? AS JSONB),CAST(? AS JSONB))""",
            (batch_id, row["excel_row"], row["source_tt"], row["source_unit_name"],
             row["canonical"]["entity"]["unit_code"], row["status"], _json(messages),
             _json(row["raw_data"]), _json(row["canonical"])),
        )

    if mode == "stage_only":
        con.execute(
            """INSERT INTO audit_logs(record_id,user_id,action,detail,created_at,module,object_type,object_id)
               VALUES(NULL,?,'Import OCOP staging',?,CURRENT_TIMESTAMP,'ocop','ocop_import_batch',?)""",
            (session["user_id"], _json({"batch_id": batch_id, "filename": preview["filename"], "errors": preview["error_rows"]}), str(batch_id)),
        )
        return {"batch_id": batch_id, "already_published": False, "published_products": 0}

    published_products = 0
    for row in preview["rows"]:
        canonical = row["canonical"]
        entity = canonical["entity"]
        product = canonical["product"]
        _ensure_entity(con, session, entity)
        product_id = _ensure_product(con, session, entity, product)
        current_id = _upsert_recognitions(
            con, product_id, product, canonical["recognitions"], batch_id, row["excel_row"]
        )
        _publish_qd5277(con, entity, product, current_id)
        published_products += 1

    con.execute(
        """INSERT INTO audit_logs(record_id,user_id,action,detail,created_at,module,object_type,object_id)
           VALUES(NULL,?,'Import OCOP Excel',?,CURRENT_TIMESTAMP,'ocop','ocop_import_batch',?)""",
        (session["user_id"], _json({
            "batch_id": batch_id,
            "filename": preview["filename"],
            "products": published_products,
            "recognitions": preview["recognition_count"],
        }), str(batch_id)),
    )
    return {"batch_id": batch_id, "already_published": False, "published_products": published_products}


def list_batches(con, limit=30):
    return [dict(row) for row in con.execute(
        """SELECT b.*,u.username FROM ocop_import_batches b
           JOIN users u ON u.id=b.imported_by ORDER BY b.id DESC LIMIT ?""", (int(limit),)
    ).fetchall()]


def list_recognitions(con, session, filters=None):
    """List recognition history with the same locality scope as OCOP products."""
    import ocop_services
    filters = filters or {}
    scope = ocop_services.get_scope(con, session)
    where = ["1=1"]
    args = []
    if scope:
        where.append("p.ma_don_vi_hanh_chinh=?")
        args.append(scope)
    unit = _text(filters.get("unit"))
    if unit and not scope:
        where.append("p.ma_don_vi_hanh_chinh=?")
        args.append(unit)
    q = _text(filters.get("q"))
    if q:
        where.append("(p.ten_san_pham ILIKE ? OR c.TenCoSo ILIKE ? OR r.decision_number ILIKE ?)")
        pattern = f"%{q}%"
        args.extend([pattern, pattern, pattern])
    year = _text(filters.get("year"))
    if year:
        try:
            year_value = int(year)
        except ValueError as exc:
            raise OcopImportError("Năm tra cứu không hợp lệ.") from exc
        where.append("r.recognition_year=?")
        args.append(year_value)
    rows = con.execute(
        """SELECT r.*,p.ten_san_pham,p.ma_san_pham,p.current_star,p.ma_don_vi_hanh_chinh,
                  c.TenCoSo AS entity_name,d.TenDonVi AS unit_name
           FROM ocop_recognitions r
           JOIN ocop_products p ON p.id=r.product_id
           JOIN DM_CoSo c ON c.Ma_CoSo=p.ma_co_so
           JOIN DM_DonViHanhChinh d ON d.Ma_DonViHanhChinh=p.ma_don_vi_hanh_chinh
           WHERE """ + " AND ".join(where) +
        " ORDER BY r.recognition_year DESC,p.ten_san_pham,r.recognition_sequence DESC,r.id DESC",
        args,
    ).fetchall()
    return [dict(row) for row in rows]


def recognitions_for_product(con, session, product_id):
    import ocop_services
    product = ocop_services.get_product(con, session, product_id)
    rows = con.execute(
        """SELECT * FROM ocop_recognitions WHERE product_id=?
           ORDER BY recognition_sequence DESC,recognition_year DESC,id DESC""", (product_id,)
    ).fetchall()
    return product, [dict(row) for row in rows]
