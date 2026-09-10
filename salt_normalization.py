"""One mapping for web sync, SQLite import and Excel ETL. No database side effects."""
from decimal import Decimal, InvalidOperation
import re

METHODS = (("land", "Truyền thống"), ("tarp", "Trải bạt"))


def exact_price(value):
    """Only a single unambiguous nonnegative price; ranges stay in raw data."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        text = str(value)
    else:
        text = str(value or "").strip()
        if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?", text):
            text = text.replace(".", "").replace(",", ".")
        elif re.fullmatch(r"\d+(?:,\d{1,2})?", text):
            text = text.replace(",", ".")
        elif not re.fullmatch(r"\d+\.\d{1,2}", text):
            return None
    try:
        price = Decimal(text)
        return price if price.is_finite() and 0 <= price <= Decimal("9999999999.99") else None
    except InvalidOperation:
        return None


def method_values(record):
    """Yield nonempty methods, preserving missing/uncertain prices as None."""
    for suffix, method in METHODS:
        area = Decimal(str(record.get("area_" + suffix) or 0))
        production = Decimal(str(record.get("harvest_" + suffix) or 0))
        if not area.is_finite() or not production.is_finite() or area < 0 or production < 0:
            raise ValueError("Diện tích/sản lượng phải là số hữu hạn không âm.")
        raw_price = record.get("price_" + suffix)
        price = exact_price(raw_price)
        # A price-only observation is still data. Preserve a range in raw records.
        has_raw_price = price is None and str(raw_price or "").strip() not in ("", "-")
        if area or production or price or has_raw_price:
            yield method, area.quantize(Decimal(".01")), production.quantize(Decimal(".01")), price


def sync_methods(execute, unit_code, time_code, record, *, postgres=False):
    """Caller owns the transaction. Only replace the two managed derived methods."""
    rows = list(method_values(dict(record))) if record else []
    for method, area, production, price in rows:
        execute("""INSERT INTO DN_SanLuongMuoi
            (Ma_DonViHanhChinh,Ma_ThoiGian,PhuongPhapSX,DienTich,SanLuong,GiaBanBinhQuan)
            VALUES(?,?,?,?,?,?)
            ON CONFLICT(Ma_DonViHanhChinh,Ma_ThoiGian,PhuongPhapSX) DO UPDATE SET
              DienTich=excluded.DienTich, SanLuong=excluded.SanLuong,
              GiaBanBinhQuan=excluded.GiaBanBinhQuan""",
            (unit_code, time_code, method, float(area), float(production),
             float(price) if price is not None else (None if postgres else 0)))
    present = {row[0] for row in rows}
    for _, method in METHODS:
        if method not in present:
            execute("""DELETE FROM DN_SanLuongMuoi WHERE Ma_DonViHanhChinh=?
                AND Ma_ThoiGian=? AND PhuongPhapSX=?""", (unit_code, time_code, method))
