"""OCOP workbook preview/import and QD 5277 synchronization."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import hashlib
import io
import re

from openpyxl import load_workbook


class OcopImportError(ValueError):
    pass


def _text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _date(value):
    if isinstance(value, (datetime, date)):
        return value.date() if isinstance(value, datetime) else value
    token = _text(value)
    if not token:
        return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(token, fmt).date()
        except ValueError:
            pass
    return None


def _number(value):
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        match = re.search(r"\d+", _text(value))
        return int(match.group()) if match else None


def _resolve_formula(ws, value, row, column, seen=None):
    if not (isinstance(value, str) and value.startswith("=")):
        return value
    seen = set(seen or ())
    key = (row, column)
    if key in seen:
        return None
    seen.add(key)
    match = re.fullmatch(r"=([A-Z]{1,3})(\d+)", value.strip(), re.I)
    if not match:
        return None
    ref_col, ref_row = match.group(1), int(match.group(2))
    return _resolve_formula(ws, ws[f"{ref_col}{ref_row}"].value, ref_row, ref_col, seen)


def _cell(ws, row, col, merged):
    value = ws.cell(row, col).value
    if value not in (None, ""):
        return _resolve_formula(ws, value, row, ws.cell(row, col).column_letter)
    for rng in merged:
        if rng.min_row <= row <= rng.max_row and rng.min_col <= col <= rng.max_col:
            top = ws.cell(rng.min_row, rng.min_col).value
            return _resolve_formula(ws, top, rng.min_row, ws.cell(rng.min_row, rng.min_col).column_letter)
    return value


def parse_ocop_workbook(file_bytes, filename):
    try:
        book = load_workbook(io.BytesIO(file_bytes), data_only=False, read_only=False)
    except Exception as exc:
        raise OcopImportError(f"Không đọc được file Excel: {exc}") from exc
    try:
        sheet_name = "Loc" if "Loc" in book.sheetnames else next((s for s in book.sheetnames if s.strip()), None)
        if not sheet_name:
            raise OcopImportError("Workbook không có sheet dữ liệu.")
        ws = book[sheet_name]
        merged = tuple(ws.merged_cells.ranges)
        rows, errors = [], []
        for row in range(5, ws.max_row + 1):
            ordinal = _number(_cell(ws, row, 1, merged))
            name = _text(_cell(ws, row, 2, merged))
            if not ordinal or not name:
                continue
            unit = _text(_cell(ws, row, 6, merged))
            entity_name = _text(_cell(ws, row, 5, merged))
            entity_type = _text(_cell(ws, row, 4, merged))
            address = _text(_cell(ws, row, 7, merged))
            representative = _text(_cell(ws, row, 8, merged))
            phone = _text(_cell(ws, row, 9, merged))
            current_star = _number(_cell(ws, row, 10, merged))
            expires_on = _date(_cell(ws, row, 11, merged))
            rec1_star = _number(_cell(ws, row, 12, merged))
            rec1_date = _date(_cell(ws, row, 13, merged))
            rec1_year = _number(_cell(ws, row, 14, merged)) or (rec1_date.year if rec1_date else None)
            rec1_decision = _text(_cell(ws, row, 15, merged))
            rec1_authority = _text(_cell(ws, row, 16, merged))
            rec2_star = _number(_cell(ws, row, 17, merged))
            rec2_date = _date(_cell(ws, row, 18, merged))
            rec2_year = _number(_cell(ws, row, 19, merged)) or (rec2_date.year if rec2_date else None)
            rec2_decision = _text(_cell(ws, row, 20, merged))
            rec2_authority = _text(_cell(ws, row, 21, merged))
            if not unit:
                errors.append({"row_number": row, "field_name": "unit", "raw_value": "", "error_message": "Thiếu xã/phường."})
            if not entity_name:
                errors.append({"row_number": row, "field_name": "entity", "raw_value": "", "error_message": "Thiếu tên chủ thể."})
            rows.append({
                "excel_row": row, "product_name": name, "product_group": _text(_cell(ws, row, 3, merged)),
                "entity_type": entity_type, "entity_name": entity_name, "unit_name": unit,
                "address": address, "representative": representative, "phone": phone,
                "current_star": current_star, "expires_on": expires_on.isoformat() if expires_on else None,
                "recognitions": [
                    {"round": 1, "star": rec1_star, "recognized_on": rec1_date.isoformat() if rec1_date else None,
                     "year": rec1_year, "decision_number": rec1_decision, "issuing_authority": rec1_authority},
                    {"round": 2, "star": rec2_star, "recognized_on": rec2_date.isoformat() if rec2_date else None,
                     "year": rec2_year, "decision_number": rec2_decision, "issuing_authority": rec2_authority},
                ],
            })
        if not rows:
            raise OcopImportError("Không tìm thấy vùng dữ liệu sản phẩm trong sheet.")
        return {
            "filename": filename, "file_sha256": hashlib.sha256(file_bytes).hexdigest(),
            "sheet_name": sheet_name, "rows": rows, "errors": errors,
            "total_products": len(rows), "entity_names": len({r["entity_name"] for r in rows if r["entity_name"]}),
            "unit_names": len({r["unit_name"] for r in rows if r["unit_name"]}),
            "second_recognitions": sum(1 for r in rows if r["recognitions"][1]["recognized_on"] or r["recognitions"][1]["star"]),
        }
    finally:
        book.close()


def _next_code(con, table, prefix, column):
    rows = con.execute(f"SELECT {column} FROM {table} WHERE {column} LIKE ? ORDER BY {column} DESC", (prefix + "%",)).fetchall()
    max_value = 0
    for row in rows:
        match = re.search(r"(\d+)$", str(row[0]))
        max_value = max(max_value, int(match.group(1)) if match else 0)
    return f"{prefix}{max_value + 1:0{10-len(prefix)}d}"


def _unit_code(con, name):
    row = con.execute("SELECT temp_code FROM admin_unit_code_mapping WHERE source_name=?", (name,)).fetchone()
    if row:
        return row[0]
    code = _next_code(con, "admin_unit_code_mapping", "TMP", "temp_code")
    con.execute("INSERT INTO DM_DonViHanhChinh(Ma_DonViHanhChinh,TenDonVi,CapHanhChinh,TinhTrang) VALUES(?,?,?,TRUE) ON CONFLICT DO NOTHING", (code, name, "xa"))
    con.execute("INSERT INTO admin_unit_code_mapping(temp_code,source_name) VALUES(?,?)", (code, name))
    return code


def _time_code(con, year):
    code = f"OCOP{int(year):04d}"
    con.execute("INSERT INTO DM_KhoangThoiGian(Ma_ThoiGian,Nam) VALUES(?,?) ON CONFLICT DO NOTHING", (code, year))
    return code


def commit_ocop_preview(con, session, preview, now):
    if preview.get("errors"):
        raise OcopImportError("Preview còn dòng lỗi; chưa thể import.")
    duplicate = con.execute("SELECT id FROM ocop_import_batches WHERE file_sha256=? AND sheet_name=?", (preview["file_sha256"], preview["sheet_name"])).fetchone()
    if duplicate:
        raise OcopImportError("File này đã được import trước đó cho cùng sheet.")
    batch = con.execute("INSERT INTO ocop_import_batches(filename,file_sha256,sheet_name,total_rows,error_rows,imported_by,imported_at) VALUES(?,?,?,?,?,?,?)", (preview["filename"], preview["file_sha256"], preview["sheet_name"], len(preview["rows"]), 0, session.get("user_id"), now))
    batch_id = batch.lastrowid
    inserted = updated = 0
    for item in preview["rows"]:
        unit_code = _unit_code(con, item["unit_name"])
        entity_code = con.execute("SELECT Ma_CoSo FROM DM_CoSo WHERE TenCoSo=? AND Ma_DonViHanhChinh=?", (item["entity_name"], unit_code)).fetchone()
        if entity_code:
            entity_code = entity_code[0]
            con.execute("UPDATE DM_CoSo SET LoaiCoSo=?,DiaChi=? WHERE Ma_CoSo=?", (item["entity_type"], item["address"], entity_code))
        else:
            entity_code = _next_code(con, "DM_CoSo", "CS", "Ma_CoSo")
            con.execute("INSERT INTO DM_CoSo(Ma_CoSo,TenCoSo,LoaiCoSo,DiaChi,Ma_DonViHanhChinh) VALUES(?,?,?,?,?)", (entity_code, item["entity_name"], item["entity_type"], item["address"], unit_code))
        entity = con.execute("SELECT id FROM ocop_entities WHERE ma_co_so=?", (entity_code,)).fetchone()
        if entity:
            entity_id = entity[0]
            con.execute("UPDATE ocop_entities SET representative_name=?,phone=?,updated_at=?,archived_at=NULL WHERE id=?", (item["representative"], item["phone"], now, entity_id))
        else:
            entity_id = con.execute("INSERT INTO ocop_entities(ma_co_so,representative_name,phone,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?)", (entity_code, item["representative"], item["phone"], session.get("user_id"), now, now)).lastrowid
        product = con.execute("SELECT id,ma_san_pham FROM ocop_products WHERE ma_co_so=? AND lower(ten_san_pham)=lower(?)", (entity_code, item["product_name"])).fetchone()
        if product:
            product_id, product_code = product[0], product[1]
            con.execute("UPDATE ocop_products SET product_group=?,current_star=?,ma_don_vi_hanh_chinh=?,updated_at=?,status='active' WHERE id=?", (item["product_group"], item["current_star"], unit_code, now, product_id))
            updated += 1
        else:
            product_code = _next_code(con, "DM_SanPham", "SP", "Ma_SanPham")
            con.execute("INSERT INTO DM_SanPham(Ma_SanPham,TenSanPham,NhomSanPham,TrangThai) VALUES(?,?,?,TRUE)", (product_code, item["product_name"], item["product_group"]))
            product_id = con.execute("INSERT INTO ocop_products(ma_san_pham,ma_co_so,ma_don_vi_hanh_chinh,ten_san_pham,product_group,current_star,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)", (product_code, entity_code, unit_code, item["product_name"], item["product_group"], item["current_star"], session.get("user_id"), now, now)).lastrowid
            inserted += 1
        con.execute("DELETE FROM ocop_recognitions WHERE product_id=?", (product_id,))
        for rec in item["recognitions"]:
            if not (rec["recognized_on"] or rec["star"] or rec["decision_number"]):
                continue
            recognized = rec["recognized_on"] or None
            con.execute("INSERT INTO ocop_recognitions(product_id,recognition_round,star,recognized_on,decision_number,issuing_authority,expires_on) VALUES(?,?,?,?,?,?,?)", (product_id, rec["round"], rec["star"], recognized, rec["decision_number"] or None, rec["issuing_authority"] or None, item["expires_on"]))
            if rec["year"]:
                _time_code(con, rec["year"])
        current_year = next((r["year"] for r in reversed(item["recognitions"]) if r["year"]), None)
        if current_year:
            time_code = _time_code(con, current_year)
            ocop_id = con.execute("SELECT COALESCE(MAX(Ma_OCOP),0)+1 FROM PTNT_OCOP").fetchone()[0]
            con.execute("INSERT INTO PTNT_OCOP(Ma_OCOP,Ma_DonViHanhChinh,Ma_ThoiGian,Ma_SanPham,TenSanPham,XepHang,ChuTheSXKD,DoanhThuNam,TrangThai) VALUES(?,?,?,?,?,?,?,NULL,NULL) ON CONFLICT(Ma_SanPham,Ma_ThoiGian) DO UPDATE SET Ma_DonViHanhChinh=EXCLUDED.Ma_DonViHanhChinh,TenSanPham=EXCLUDED.TenSanPham,XepHang=EXCLUDED.XepHang,ChuTheSXKD=EXCLUDED.ChuTheSXKD", (ocop_id, unit_code, time_code, product_code, item["product_name"], str(item["current_star"]) if item["current_star"] else None, item["entity_name"]))
    con.execute("UPDATE ocop_import_batches SET imported_rows=?,updated_rows=? WHERE id=?", (inserted, updated, batch_id))
    return {"batch_id": batch_id, "inserted": inserted, "updated": updated, "skipped": 0, "errors": 0}
