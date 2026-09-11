"""Command-line OCOP Excel importer for the shared PostgreSQL database."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import backend_db
from ocop_import import commit_ocop_preview, parse_ocop_workbook


def main():
    parser = argparse.ArgumentParser(description="Import workbook OCOP into PostgreSQL")
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--user-id", type=int, default=1)
    args = parser.parse_args()
    if not args.workbook.is_file():
        parser.error(f"Không tìm thấy workbook: {args.workbook}")
    preview = parse_ocop_workbook(args.workbook.read_bytes(), args.workbook.name)
    con = backend_db.compat_connect()
    try:
        con.execute("BEGIN")
        result = commit_ocop_preview(con, {"user_id": args.user_id}, preview, "cli")
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    print({"products": preview["total_products"], "entities": preview["entity_names"], "units": preview["unit_names"], **result})


if __name__ == "__main__":
    main()
