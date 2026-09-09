"""Read-only/rollback integration checks for the PostgreSQL cutover."""

import unittest
from uuid import uuid4

import server
from backend_db import translate_sql


class PostgreSQLTranslationTests(unittest.TestCase):
    def test_sqlite_null_safe_inequality_is_translated(self):
        sql, _ = translate_sql("UPDATE ocop_applications SET criteria_set_id=? WHERE criteria_set_id IS NOT ?")
        self.assertIn("criteria_set_id IS DISTINCT FROM %s", sql)


@unittest.skipUnless(server.using_postgres(), "PostgreSQL runtime is not enabled")
class PostgreSQLBackendTests(unittest.TestCase):
    def test_migrated_counts_and_local_authentication(self):
        con = server.db_conn()
        try:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM users").fetchone()[0], 10)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM records").fetchone()[0], 24)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0], 25)
            user = server.find_active_user(con, "chicuc")
            self.assertIsNotNone(user)
            self.assertTrue(user["password_hash"])
        finally:
            con.rollback()
            con.close()

    def test_latest_cumulative_report_wins_monthly_sync(self):
        con = server.db_conn()
        try:
            user_id = server.create_user(
                con, "probe_" + uuid4().hex, server.hash_password("probe123"),
                "unit", "Xã An Thới Đông", server.now_text(),
            )
            record_ids = []
            for day, area_land, area_tarp, harvest_land, harvest_tarp in (
                ("2099-04-07", 10, 2, 100, 20),
                ("2099-04-28", 15, 3, 180, 30),
            ):
                cursor = con.execute(
                    """INSERT INTO records
                       (report_date,reporting_mode,unit_name,ma_don_vi_hanh_chinh,
                        created_by,area_land,area_tarp,harvest_land,harvest_tarp,
                        status,created_at,updated_at)
                       VALUES(?,'cumulative','Xã An Thới Đông','27673',?,?,?,?,?,
                              'approved',?,?)""",
                    (day, user_id, area_land, area_tarp, harvest_land, harvest_tarp,
                     server.now_text(), server.now_text()),
                )
                record_ids.append(cursor.lastrowid)
            latest = con.execute("SELECT * FROM records WHERE id=?", (record_ids[-1],)).fetchone()
            server.sync_standard_salt_record(con, latest)
            rows = con.execute(
                """SELECT PhuongPhapSX,DienTich,SanLuong,GiaBanBinhQuan
                   FROM DN_SanLuongMuoi
                   WHERE Ma_DonViHanhChinh='27673' AND Ma_ThoiGian='2099-04'"""
            ).fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["PhuongPhapSX"], "Truyền thống")
            self.assertEqual(float(rows[0]["DienTich"]), 18)
            self.assertEqual(float(rows[0]["SanLuong"]), 210)
            self.assertIsNone(rows[0]["GiaBanBinhQuan"])
        finally:
            con.rollback()
            con.close()


if __name__ == "__main__":
    unittest.main()
