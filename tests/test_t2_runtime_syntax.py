"""Catch syntax regressions in T2 web/CLI entry points that unit tests do not import."""
from pathlib import Path
import py_compile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class T2RuntimeSyntaxTests(unittest.TestCase):
    def test_t2_entry_points_compile(self):
        for relative in (
            "server_t2.py",
            "ocop_import_pages.py",
            "database/etl/import_ocop_legacy.py",
        ):
            with self.subTest(file=relative):
                py_compile.compile(str(ROOT / relative), doraise=True)


if __name__ == "__main__":
    unittest.main()
