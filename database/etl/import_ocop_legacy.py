#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate, stage, or publish the historical OCOP workbook.

Examples:
  python database/etl/import_ocop_legacy.py --workbook "CCPTNT OCOP.xlsx" --actor "Nhat Minh" --validate-only
  python database/etl/import_ocop_legacy.py --workbook "CCPTNT OCOP.xlsx" --actor "Nhat Minh" --stage-only
  python database/etl/import_ocop_legacy.py --workbook "CCPTNT OCOP.xlsx" --actor "Nhat Minh" --publish
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import admin_units
from backend_db import compat_connect
import ocop_import
from permissions import is_chi_cuc_user


def actor_session(con, username: str):
    row = con.execute(
        "SELECT id,username,role,unit_name,active FROM users WHERE username=?",
        (username,),
    ).fetchone()
    if not row or not row["active"]:
        raise SystemExit("Không tìm thấy tài khoản đang hoạt động.")
    session = dict(row)
    session["user_id"] = session.pop("id")
    if not is_chi_cuc_user(session):
        raise SystemExit("--actor phải là tài khoản admin hoặc staff của Chi cục.")
    return session


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--actor", required=True, help="Tên đăng nhập admin/staff dùng để ghi audit")
    parser.add_argument("--sheet", default=ocop_import.DEFAULT_SHEET)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--validate-only", action="store_true")
    mode.add_argument("--stage-only", action="store_true")
    mode.add_argument("--publish", action="store_true")
    args = parser.parse_args()

    if not args.workbook.is_file():
        parser.error(f"Không tìm thấy workbook: {args.workbook}")
    file_bytes = args.workbook.read_bytes()
    con = compat_connect()
    try:
        session = actor_session(con, args.actor)
        preview = ocop_import.parse_ocop_workbook(
            file_bytes,
            args.workbook.name,
            admin_units.unit_lookup(con),
            args.sheet,
        )
        summary = {key: preview[key] for key in (
            "filename", "sheet_name", "total_rows", "valid_rows", "warning_rows", "error_rows",
            "source_unit_count", "mapped_unit_count", "entity_count", "product_count", "recognition_count",
        )}
        summary["unknown_units"] = preview["unknown_units"]
        if args.validate_only or not (args.stage_only or args.publish):
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 2 if preview["error_rows"] else 0

        con.execute("BEGIN")
        try:
            result = ocop_import.commit_ocop_preview(
                con, session, preview, "publish" if args.publish else "stage_only"
            )
            con.commit()
        except Exception:
            con.rollback()
            raise
        print(json.dumps({**summary, **result}, ensure_ascii=False, indent=2, default=str))
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
