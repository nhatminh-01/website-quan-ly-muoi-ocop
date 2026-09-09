"""Create a separate development snapshot; never overwrite either database."""
from pathlib import Path
import hashlib
import sqlite3


def prepare():
    root = Path(__file__).resolve().parent
    source = root / "salt_management.db"
    target = root / "salt_management_TEST.db"
    if not source.is_file():
        raise SystemExit("Khong tim thay database nguon.")
    if target.exists():
        print("Da co salt_management_TEST.db; giu nguyen, khong ghi de.")
        return
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    # Exclusive creation prevents accidentally replacing a supplied test database.
    with target.open("xb"):
        pass
    try:
        with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as src:
            with sqlite3.connect(target) as dst:
                src.backup(dst)
                result = dst.execute("PRAGMA integrity_check").fetchone()[0]
                if result != "ok":
                    raise RuntimeError("Database test khong vuot qua kiem tra toan ven.")
        if hashlib.sha256(source.read_bytes()).hexdigest() != before:
            raise RuntimeError("Database nguon thay doi trong luc sao luu; can kiem tra lai.")
    except Exception:
        # Leave the failed snapshot for inspection; never delete source data.
        raise
    print("Da tao salt_management_TEST.db. Database nguon khong thay doi.")


if __name__ == "__main__":
    prepare()
