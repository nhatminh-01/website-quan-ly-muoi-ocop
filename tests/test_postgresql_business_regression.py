"""Business regressions that must survive the PostgreSQL-only cutover."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import unittest
from uuid import uuid4

import backend_db
import admin_units
import ocop_services
import permissions
import server
from weekly_import import commit_weekly_preview, effective_weekly_dashboard


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = (
    "002_qd5277_schema.sql",
    "004_app_schema.sql",
    "005_monthly_salt_sync.sql",
    "006_official_admin_units.sql",
    "007_ocop_init_only.sql",
    "008_ocop_dynamic_criteria.sql",
    "009_staff_role.sql",
    "010_weekly_salt_imports.sql",
    "011_weekly_foundation.sql",
    "012_admin_units.sql",
)


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def weekly_preview(*, week: str, report_date: str, sha_label: str,
                   area_land: float, area_tarp: float,
                   harvest_land: float, harvest_tarp: float):
    canonical = {
        "week_code": week,
        "report_date": report_date,
        "unit_name": "Xã Tân Nhựt",
        "ma_don_vi_hanh_chinh": "27595",
        "phuong_phap_sx": "Truyền thống",
        "gia_ban_binh_quan": None,
        "dien_tich": area_land + area_tarp,
        "san_luong": harvest_land + harvest_tarp,
        "area_land": area_land,
        "area_tarp": area_tarp,
        "harvest_land": harvest_land,
        "harvest_tarp": harvest_tarp,
        "sold_land": 10,
        "sold_tarp": 5,
        "sold_total": 15,
        "remaining_land": 20,
        "remaining_tarp": 10,
        "remaining_total": 30,
        "processed_fine": 2,
        "processed_iodized": 1,
        "households": 10,
        "workers": 20,
        "price_land": "1000",
        "price_tarp": "1200",
        "damage_land": 0,
        "damage_tarp": 0,
        "note": "",
    }
    return {
        "filename": f"{week}.xlsx",
        "file_sha256": _sha(sha_label),
        "sheet_name": "Bao cao tuan",
        "week_code": week,
        "report_date": report_date,
        "rows": [{
            "excel_row": 5,
            "unit_name_raw": "Xã Tân Nhựt",
            "status": "valid",
            "errors": [],
            "warnings": [],
            "raw_data": {},
            "canonical": canonical,
        }],
        "valid_rows": 1,
        "warning_rows": 0,
        "error_rows": 0,
    }


class PostgreSQLCompatibilityContractTests(unittest.TestCase):
    def test_boolean_literals_are_adapted_without_changing_business_sql(self):
        sql, _ = backend_db.translate_sql(
            "SELECT * FROM users u JOIN DM_DonViHanhChinh d ON TRUE "
            "WHERE u.active=1 AND d.TinhTrang = 0"
        )
        self.assertIn("u.active=TRUE", sql)
        self.assertIn("d.TinhTrang=FALSE", sql)

    def test_roles_remain_distinct(self):
        self.assertTrue(permissions.is_admin({"role": "admin"}))
        self.assertTrue(permissions.is_chi_cuc_user({"role": "staff"}))
        self.assertFalse(permissions.can_manage_users({"role": "staff"}))
        self.assertFalse(permissions.is_chi_cuc_user({"role": "unit"}))


@unittest.skipUnless(os.getenv("OCOP_TEST_PG_DSN"),
                     "Set OCOP_TEST_PG_DSN to enable disposable PostgreSQL tests")
class PostgreSQLBusinessRegressionTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg import sql

        self.psycopg = psycopg
        self.admin_dsn = os.environ["OCOP_TEST_PG_DSN"]
        self.database = "ocop_business_" + uuid4().hex
        with psycopg.connect(self.admin_dsn, autocommit=True) as admin:
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(self.database)))
        self.addCleanup(self.drop_database)

        raw = self.connection()
        try:
            for name in MIGRATIONS:
                raw.execute((ROOT / "database" / "sql" / name).read_text(encoding="utf-8"))
        finally:
            raw.close()

    def drop_database(self):
        from psycopg import sql

        with self.psycopg.connect(self.admin_dsn, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(
                sql.Identifier(self.database)))

    def connection(self):
        return self.psycopg.connect(
            self.admin_dsn,
            dbname=self.database,
            autocommit=True,
            row_factory=backend_db.hybrid_row,
            options="-c search_path=app,qd5277,staging,public",
        )

    def compat(self):
        return backend_db.CompatConnection(self.connection())

    def create_user(self, con, username, role, unit_code=None):
        user_id = con.execute(
            "INSERT INTO users(username,role,active,created_at) "
            "VALUES(?,?,TRUE,'2026-09-11 00:00:00')",
            (username, role),
        ).lastrowid
        if unit_code:
            con.execute(
                "INSERT INTO user_admin_units(user_id,ma_don_vi_hanh_chinh) VALUES(?,?)",
                (user_id, unit_code),
            )
            con.execute(
                "UPDATE users SET unit_name=(SELECT TenDonVi FROM DM_DonViHanhChinh "
                "WHERE Ma_DonViHanhChinh=?) WHERE id=?",
                (unit_code, user_id),
            )
        con.commit()
        return user_id

    def test_admin_units_tan_nhut_alias_and_backend_permissions(self):
        con = self.compat()
        try:
            admin_id = self.create_user(con, "admin_test", "admin")
            staff_id = self.create_user(con, "staff_test", "staff")
            tan_nhut = admin_units.get_unit(con, "27595")
            self.assertIsNotNone(tan_nhut)
            self.assertEqual(tan_nhut["name"], "Xã Tân Nhựt")
            self.assertTrue(tan_nhut["active"])
            self.assertEqual(admin_units.unit_lookup(con)("Xã An Thời Đông"),
                             ("Xã An Thới Đông", "27673"))
            admin_units.require_admin(con, {"user_id": admin_id, "role": "admin"})
            with self.assertRaises(admin_units.CatalogError) as blocked:
                admin_units.require_admin(con, {"user_id": staff_id, "role": "staff"})
            self.assertEqual(blocked.exception.status, 403)
        finally:
            con.close()

    def test_ocop_boolean_queries_and_unit_scope_work_on_postgresql(self):
        con = self.compat()
        try:
            admin_id = self.create_user(con, "ocop_admin", "admin")
            unit_id = self.create_user(con, "ocop_unit", "unit", "27595")
            admin_session = {"user_id": admin_id, "role": "admin", "unit_name": "Chi cục"}
            unit_session = {"user_id": unit_id, "role": "unit", "unit_name": "Xã Tân Nhựt"}

            admin_units_rows = ocop_services.unit_options(con, admin_session)
            self.assertTrue(any(row["code"] == "27595" for row in admin_units_rows))
            scoped = ocop_services.unit_options(con, unit_session)
            self.assertEqual([row["code"] for row in scoped], ["27595"])

            criteria = ocop_services.criteria_set_options(con, admin_session)
            self.assertEqual(len(criteria), 26)
            self.assertEqual(criteria[9]["code"], "QD26-10")

            html = server.ocop_access_page(con, admin_session)
            self.assertIn("ocop_unit", html)
            self.assertIn("Xã Tân Nhựt", html)
        finally:
            con.close()

    def test_weekly_skip_update_and_previous_distinct_week(self):
        con = self.compat()
        try:
            staff_id = self.create_user(con, "weekly_staff", "staff")
            session = {"user_id": staff_id, "role": "staff", "unit_name": "Chi cục"}

            w34 = weekly_preview(
                week="2026-W34", report_date="2026-08-21", sha_label="w34-first",
                area_land=70, area_tarp=30, harvest_land=600, harvest_tarp=400,
            )
            first = commit_weekly_preview(con, session, w34, "update", "2026-09-11 08:00:00")
            con.commit()
            self.assertEqual(first["inserted"], 1)

            w34_skip = weekly_preview(
                week="2026-W34", report_date="2026-08-21", sha_label="w34-skip",
                area_land=90, area_tarp=10, harvest_land=900, harvest_tarp=100,
            )
            skipped = commit_weekly_preview(con, session, w34_skip, "skip", "2026-09-11 08:05:00")
            con.commit()
            self.assertEqual(skipped["skipped"], 1)
            row = con.execute(
                "SELECT area_land,area_tarp,harvest_land,harvest_tarp,phuong_phap_sx "
                "FROM salt_weekly_records WHERE week_code='2026-W34' AND ma_don_vi_hanh_chinh='27595'"
            ).fetchone()
            self.assertEqual(float(row["area_land"]), 70.0)
            self.assertEqual(row["phuong_phap_sx"], "Truyền thống")

            w34_update = weekly_preview(
                week="2026-W34", report_date="2026-08-21", sha_label="w34-update",
                area_land=80, area_tarp=20, harvest_land=700, harvest_tarp=300,
            )
            updated = commit_weekly_preview(con, session, w34_update, "update", "2026-09-11 08:10:00")
            con.commit()
            self.assertEqual(updated["updated"], 1)
            row = con.execute(
                "SELECT area_land,area_tarp FROM salt_weekly_records "
                "WHERE week_code='2026-W34' AND ma_don_vi_hanh_chinh='27595'"
            ).fetchone()
            self.assertEqual((float(row[0]), float(row[1])), (80.0, 20.0))

            w35 = weekly_preview(
                week="2026-W35", report_date="2026-08-28", sha_label="w35",
                area_land=85, area_tarp=15, harvest_land=720, harvest_tarp=280,
            )
            commit_weekly_preview(con, session, w35, "update", "2026-09-11 08:15:00")
            con.commit()

            dashboard = effective_weekly_dashboard(con, week="2026-W35")
            self.assertEqual(dashboard["selected"]["week_code"], "2026-W35")
            self.assertEqual(dashboard["previous"]["week_code"], "2026-W34")
            self.assertEqual(len(dashboard["rows"]), 1)
            self.assertEqual(len(dashboard["previous_rows"]), 1)
        finally:
            con.close()


if __name__ == "__main__":
    unittest.main()
