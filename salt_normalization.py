"""One mapping for web sync, SQLite import and Excel ETL. No database side effects."""
from decimal import Decimal, InvalidOperation
import re

TRADITIONAL_METHOD = "Truyền thống"
# Older builds incorrectly projected the crystallizer foundation "trải bạt"
# as a separate production method. It is removed whenever the derived row is
# rebuilt; a genuine "Công nghiệp" row, if introduced later, is left intact.
LEGACY_DERIVED_METHODS = ("Trải bạt",)


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
    """Yield one QD 5277 row; land/tarp are foundations of traditional salt."""
    foundation_area = Decimal("0")
    foundation_production = Decimal("0")
    for suffix in ("land", "tarp"):
        area_value = Decimal(str(record.get("area_" + suffix) or 0))
        production_value = Decimal(str(record.get("harvest_" + suffix) or 0))
        if (not area_value.is_finite() or not production_value.is_finite()
                or area_value < 0 or production_value < 0):
            raise ValueError("Diện tích/sản lượng phải là số hữu hạn không âm.")
        foundation_area += area_value
        foundation_production += production_value
    # Excel has official total columns C/F. app.records has no stored total, so
    # its standard projection is calculated from the two foundation details.
    area = Decimal(str(record["area_total"])) if record.get("area_total") is not None else foundation_area
    production = Decimal(str(record["harvest_total"])) if record.get("harvest_total") is not None else foundation_production
    if not area.is_finite() or not production.is_finite() or area < 0 or production < 0:
        raise ValueError("Tổng diện tích/sản lượng phải là số hữu hạn không âm.")
    if area or production:
        # Source prices describe each foundation separately and can be ranges.
        # QD 5277 has only one average-price field, so do not invent an average.
        yield (TRADITIONAL_METHOD, area.quantize(Decimal(".01")),
               production.quantize(Decimal(".01")), None)


def sync_methods(execute, unit_code, time_code, record, *, postgres=False):
    """Caller owns the transaction. Upsert one aggregated traditional row."""
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
    for method in (TRADITIONAL_METHOD, *LEGACY_DERIVED_METHODS):
        if method not in present:
            execute("""DELETE FROM DN_SanLuongMuoi WHERE Ma_DonViHanhChinh=?
                AND Ma_ThoiGian=? AND PhuongPhapSX=?""", (unit_code, time_code, method))
