"""Validate the Excel source, staging import, and QD 5277 target rows."""

from __future__ import annotations

import argparse
import csv
import math
import os
import sys
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv
from openpyxl import load_workbook


SHEET_NAME = "21.8-Tuan 34"
DATA_ROWS = range(6, 14)
SUM_TOLERANCE = Decimal("0.01")
PRODUCTIVITY_TOLERANCE = Decimal("0.10")
EXPECTED = {
    "C": Decimal("1953.8"), "D": Decimal("356.4"), "E": Decimal("1597.5"),
    "F": Decimal("134537"), "G": Decimal("22392"), "H": Decimal("112145"),
    "I": Decimal("92297.6"), "L": Decimal("42239.4"),
    "R": Decimal("912"), "S": Decimal("2083"),
    "W": Decimal("6340"), "Z": Decimal("1773.3"),
}
CHECKS = [("C", "D", "E"), ("F", "G", "H"), ("I", "J", "K"),
          ("L", "M", "N"), ("W", "X", "Y")]
UNMAPPED_COLUMNS = [
    "A - TT", "D/E - diện tích muối đất/trải bạt (chi tiết nền kết tinh)",
    "G/H - sản lượng thu hoạch muối đất/trải bạt", "I/J/K - sản lượng tiêu thụ",
    "L/M/N - sản lượng còn lại", "O/P/Q - sản lượng chế biến", "R - số hộ",
    "S - số lao động", "T/U - giá bán riêng", "V - năng suất bình quân",
    "W/X/Y - thiệt hại do mưa trái mùa", "Z - diện tích mất trắng",
    "AA - ghi chú/ngày mưa", "AB - thời gian kết thúc niên vụ",
]


@dataclass
class Issue:
    sheet: str
    excel_row: int | str
    dia_ban: str
    field: str
    raw_value: str
    expected_value: str
    difference: str
    severity: str
    message: str


def conn_kwargs() -> dict[str, Any]:
    return {
        "host": os.getenv("PGHOST", "localhost"), "port": int(os.getenv("PGPORT", "5432")),
        "dbname": os.getenv("PGDATABASE", "ptnt_qd5277_dev"),
        "user": os.getenv("PGUSER", "postgres"), "password": os.getenv("PGPASSWORD") or None,
    }


def decimal_for_math(value: Any, *, blank_as_zero: bool = True) -> Decimal:
    if value is None or value == "-":
        if blank_as_zero:
            return Decimal(0)
        raise InvalidOperation
    if isinstance(value, bool):
        raise InvalidOperation
    return Decimal(str(value))


def show(value: Any) -> str:
    if value is None:
        return "<blank>"
    return str(value)


def add_marker_issues(issues: list[Issue], row: int, dia_ban: str, ws: Any) -> None:
    for col in range(1, 29):
        value = ws.cell(row, col).value
        letter = ws.cell(row, col).column_letter
        if value is None:
            issues.append(Issue(SHEET_NAME, row, dia_ban, letter, "<blank>", "",
                                "", "INFO", "Ô nguồn để trống; staging giữ NULL, chỉ coi là 0 trong phép kiểm tra tổng."))
        elif value == "-":
            issues.append(Issue(SHEET_NAME, row, dia_ban, letter, "-", "",
                                "", "INFO", "Dấu '-' được giữ nguyên trong staging, chỉ coi là 0 trong phép kiểm tra tổng."))


def validate_source(workbook: Path) -> tuple[list[Issue], dict[str, Decimal]]:
    formulas = load_workbook(workbook, data_only=False, read_only=True)
    cached = load_workbook(workbook, data_only=True, read_only=True)
    wf, wv = formulas[SHEET_NAME], cached[SHEET_NAME]
    issues: list[Issue] = []
    totals = {key: Decimal(0) for key in EXPECTED}

    for row in DATA_ROWS:
        dia_ban = str(wv.cell(row, 2).value or "")
        add_marker_issues(issues, row, dia_ban, wv)
        for total_col, left_col, right_col in CHECKS:
            values = [wv[f"{c}{row}"].value for c in (total_col, left_col, right_col)]
            try:
                actual = decimal_for_math(values[0])
                expected = decimal_for_math(values[1]) + decimal_for_math(values[2])
            except (InvalidOperation, ValueError):
                issues.append(Issue(SHEET_NAME, row, dia_ban, total_col, show(values[0]),
                                    f"{show(values[1])} + {show(values[2])}", "", "ERROR",
                                    "Sai kiểu dữ liệu trong phép kiểm tra tổng."))
                continue
            diff = actual - expected
            if abs(diff) > SUM_TOLERANCE:
                issues.append(Issue(SHEET_NAME, row, dia_ban, total_col, show(values[0]),
                                    str(expected), str(diff), "ERROR",
                                    f"Không khớp {total_col} = {left_col} + {right_col}. Không sửa dữ liệu nguồn."))
            formula = wf[f"{total_col}{row}"].value
            if isinstance(formula, str) and formula.startswith("=") and abs(diff) > SUM_TOLERANCE:
                issues.append(Issue(SHEET_NAME, row, dia_ban, total_col, formula,
                                    str(expected), str(diff), "ERROR",
                                    "Giá trị cached của công thức không khớp phép tính kiểm tra."))

        try:
            area = decimal_for_math(wv[f"C{row}"].value, blank_as_zero=False)
            production = decimal_for_math(wv[f"F{row}"].value, blank_as_zero=False)
            productivity = decimal_for_math(wv[f"V{row}"].value, blank_as_zero=False)
            if area > 0:
                expected_productivity = production / area
                diff = productivity - expected_productivity
                if abs(diff) > PRODUCTIVITY_TOLERANCE:
                    issues.append(Issue(SHEET_NAME, row, dia_ban, "V", show(wv[f"V{row}"].value),
                                        str(expected_productivity), str(diff), "ERROR",
                                        "Năng suất Excel không khớp F/C trong tolerance 0.10 tấn/ha."))
        except (InvalidOperation, ValueError, ZeroDivisionError):
            issues.append(Issue(SHEET_NAME, row, dia_ban, "V", show(wv[f"V{row}"].value),
                                "F/C", "", "ERROR", "Không thể kiểm tra năng suất do blank, '-', hoặc sai kiểu."))

        for column in EXPECTED:
            try:
                totals[column] += decimal_for_math(wv[f"{column}{row}"].value)
            except (InvalidOperation, ValueError):
                issues.append(Issue(SHEET_NAME, row, dia_ban, column,
                                    show(wv[f"{column}{row}"].value), "numeric", "", "ERROR",
                                    "Sai kiểu dữ liệu trong cột checksum."))

    for column, expected in EXPECTED.items():
        diff = totals[column] - expected
        if abs(diff) > SUM_TOLERANCE:
            issues.append(Issue(SHEET_NAME, "TOTAL", "TỔNG CỘNG", column, str(totals[column]),
                                str(expected), str(diff), "ERROR", "Checksum nguồn không khớp giá trị kỳ vọng."))
    formulas.close()
    cached.close()
    return issues, totals


def db_metrics() -> dict[str, Any]:
    with psycopg.connect(**conn_kwargs()) as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM staging.diem_nghiep_2026_w34_raw WHERE source_sheet=%s", (SHEET_NAME,))
        staging_rows = cur.fetchone()[0]
        cur.execute("""
            SELECT COUNT(*), COALESCE(SUM(DienTich), 0), COALESCE(SUM(SanLuong), 0),
                   COUNT(*) FILTER (WHERE PhuongPhapSX = 'Truyền thống'),
                   COUNT(*) FILTER (WHERE GiaBanBinhQuan IS NULL)
            FROM qd5277.DN_SanLuongMuoi WHERE Ma_ThoiGian='2026-08'
        """)
        count, area, production, traditional, null_price = cur.fetchone()
        cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema IN ('qd5277','staging')")
        tables = cur.fetchone()[0]
    return {"staging_rows": staging_rows, "target_rows": count, "target_area": area,
            "target_production": production, "traditional_rows": traditional,
            "null_price_rows": null_price, "tables": tables}


def write_outputs(project_root: Path, issues: list[Issue], totals: dict[str, Decimal], db: dict[str, Any]) -> None:
    csv_path = project_root / "validation" / "validation_issues.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(asdict(issues[0]).keys()) if issues else list(Issue.__annotations__))
        writer.writeheader()
        writer.writerows(asdict(issue) for issue in issues)

    errors = [issue for issue in issues if issue.severity == "ERROR"]
    checksum_lines = [f"| {col} | {totals[col]} | {EXPECTED[col]} | {'PASS' if abs(totals[col]-EXPECTED[col]) <= SUM_TOLERANCE else 'FAIL'} |" for col in EXPECTED]
    fail_lines = [f"| {i.excel_row} | {i.dia_ban} | {i.field} | {i.raw_value} | {i.expected_value} | {i.difference} | {i.message} |" for i in errors]
    report = f"""# Báo cáo validation import Diêm nghiệp

## Kết quả tổng quan

- Sheet nguồn: `{SHEET_NAME}`
- Snapshot: 21/08/2026
- Số row nguồn: 8
- Số row staging: {db['staging_rows']}
- Số row `DN_SanLuongMuoi`: {db['target_rows']}
- Tổng diện tích target: {db['target_area']}
- Tổng sản lượng target: {db['target_production']}
- Record có `PhuongPhapSX = 'Truyền thống'`: {db['traditional_rows']}
- Record có `GiaBanBinhQuan IS NULL`: {db['null_price_rows']}
- Trạng thái validation: {'FAIL' if errors else 'PASS'} ({len(errors)} lỗi; các marker blank/'-' mức INFO nằm trong CSV)

## Checksum nguồn

| Cột | Thực tế | Kỳ vọng | Kết quả |
|---|---:|---:|---|
{chr(10).join(checksum_lines)}

## Row fail validation

| Excel row | Địa bàn | Field | Raw/cached | Expected | Difference | Message |
|---:|---|---|---|---|---:|---|
{chr(10).join(fail_lines) if fail_lines else '| - | - | - | - | - | - | Không có lỗi |'}

## Mapping vào QĐ 5277

- B -> `Ma_DonViHanhChinh` qua mã hành chính chính thức; alias `An Thời Đông` được sửa thành `An Thới Đông`.
- Kỳ báo cáo -> `Ma_ThoiGian = '2026-08'`.
- Business rule -> `PhuongPhapSX = 'Truyền thống'`.
- C -> `DienTich`.
- F -> `SanLuong`.
- `GiaBanBinhQuan = NULL`; không tính từ T/U.

## Cột Excel chỉ nằm trong staging

{chr(10).join(f'- {item}' for item in UNMAPPED_COLUMNS)}

## Field QĐ 5277 mà source chưa có trực tiếp

- `Ma_SanLuongMuoi`: khóa kỹ thuật tạo tuần tự 1..8 cho lần validation.
- `Ma_DonViHanhChinh`: source chỉ có tên địa bàn, được ánh xạ sang mã chính thức theo Quyết định 19/2025/QĐ-TTg.
- `Ma_ThoiGian`: suy ra từ snapshot tháng 08/2026; ngày 21/08/2026 chỉ giữ ở staging.
- `PhuongPhapSX`: áp dụng business rule đã xác nhận, không lấy trực tiếp từ một cột Excel.
- `GiaBanBinhQuan`: source chỉ có hai giá riêng T/U và chưa có quy tắc gộp, nên để NULL.

## Quy ước validation

- Tên sai `Xã An Thời Đông` trong workbook chỉ được sửa ở bước mapping; staging vẫn giữ nguyên raw source.
- Blank và `-` được giữ nguyên trong staging; chỉ được coi là 0 trong phép kiểm tra tổng.
- Tolerance tổng là 0.01; tolerance năng suất là 0.10 tấn/ha.
- Không map các trường chưa chắc chắn và không triển khai QĐ 5333/GIS.
"""
    (project_root / "validation" / "validation_report.md").write_text(report, encoding="utf-8")


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--workbook", type=Path, default=project_root / "data" / "CCPTNT Diemnghiep.xlsx")
    args = parser.parse_args()
    load_dotenv(project_root / ".env")
    issues, totals = validate_source(args.workbook)
    db = db_metrics()
    write_outputs(project_root, issues, totals, db)
    error_count = sum(issue.severity == "ERROR" for issue in issues)
    print(f"Validation hoàn tất: {error_count} lỗi; staging={db['staging_rows']}; target={db['target_rows']}")
    return 1 if error_count else 0


if __name__ == "__main__":
    sys.exit(main())
