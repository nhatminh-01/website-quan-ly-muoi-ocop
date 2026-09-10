"""Official administrative mappings for the Diem nghiep validation import."""

from __future__ import annotations

import re
import unicodedata


TIME_CODE = "2026-08"
PRODUCTION_METHODS = {"land": "Truyền thống", "tarp": "Trải bạt"}

OFFICIAL_ADMIN_CODES = {
    "Xã An Thới Đông": "27673",
    "Xã An Thời Đông": "27673",  # Alias typo trong workbook nguồn.
    "Xã Thạnh An": "27676",
    "Xã Cần Giờ": "27664",
    "Xã Long Điền": "26659",
    "Xã Long Sơn": "26545",
    "Phường Phước Thắng": "26542",
    "Phường Long Hương": "26566",
    "Phường Bà Rịa": "26560",
}


def normalize_label(value: object) -> str:
    """Normalize Unicode and whitespace without removing Vietnamese diacritics."""
    text = unicodedata.normalize("NFC", str(value or ""))
    return re.sub(r"\s+", " ", text).strip().casefold()


ADMIN_CODE_BY_NORMALIZED_NAME = {
    normalize_label(name): code for name, code in OFFICIAL_ADMIN_CODES.items()
}


def lookup_admin_code(name: object) -> str:
    key = normalize_label(name)
    try:
        return ADMIN_CODE_BY_NORMALIZED_NAME[key]
    except KeyError as exc:
        raise ValueError(f"Chưa có mapping địa bàn: {name!r}") from exc
