from pathlib import Path
import unittest

import admin_units
from database.validation.audit_hcmc_admin_units import load_reference
from database.migration.apply_pending import VERSION_RE


ROOT = Path(__file__).resolve().parents[1]


class HcmcAdminUnitReferenceTests(unittest.TestCase):
    def test_reference_has_official_168_shape_and_con_dao(self):
        reference = load_reference()
        self.assertEqual(len(reference), 168)
        self.assertEqual(sum(row["level"] == "phuong" for row in reference.values()), 113)
        self.assertEqual(sum(row["level"] == "xa" for row in reference.values()), 54)
        self.assertEqual(reference["26732"], {
            "code": "26732",
            "name": "Đặc khu Côn Đảo",
            "level": "dackhu",
            "parent_code": "79",
        })
        self.assertTrue(all(row["parent_code"] == "79" for row in reference.values()))
        self.assertTrue(all(not code.upper().startswith("TMP") for code in reference))
        self.assertEqual(admin_units.LEVELS["dackhu"], "Đặc khu")

    def test_migration_is_a_new_idempotent_catalog_migration(self):
        migration = (ROOT / "database" / "sql" / "021_hcmc_168_admin_units.sql").read_text(encoding="utf-8")
        self.assertIn("app_021_hcmc_168_admin_units", migration)
        self.assertIn("ON CONFLICT (Ma_DonViHanhChinh) DO UPDATE", migration)
        self.assertIn("TinhTrang = FALSE", migration)
        self.assertIn("ON COMMIT DROP", migration)
        self.assertNotIn("DELETE FROM", migration.upper())
        self.assertIn("app_021_hcmc_168_admin_units", VERSION_RE.findall(migration))
        bootstrap = (ROOT / "database" / "migration" / "bootstrap_production.py").read_text(encoding="utf-8")
        self.assertIn('"hcmc_168_admin_units"', bootstrap)


if __name__ == "__main__":
    unittest.main()
