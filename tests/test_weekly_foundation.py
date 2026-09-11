"""Weekly migration, effective periods, and salt totals on disposable databases."""
from contextlib import closing
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import unittest

import migrate_weekly
import server
import admin_units
from salt_normalization import method_values, sync_methods
from weekly_import import parse_weekly_workbook, commit_weekly_preview, effective_weekly_dashboard
import test_integration as integration


def preview(day, token, factor=1, names=("Xã An Thới Đông",), lookup=None):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Tuần"
    ws.append(["STT", "Đơn vị"])
    for index, name in enumerate(names, 1):
        row = [None] * 28
        row[0], row[1] = index, name
        for col, value in {3:100, 4:70, 5:30, 6:1000, 7:600, 8:400,
                           9:500, 10:300, 11:200, 12:500, 13:300, 14:200,
                           23:10, 24:6, 25:4}.items():
            row[col - 1] = value * factor
        row[19], row[20], row[26] = "1.000 - 1.500", "2.000", token
        ws.append(row)
    stream = io.BytesIO()
    wb.save(stream)
    wb.close()
    return parse_weekly_workbook(stream.getvalue(), day, "Tuần", token + ".xlsx", lookup or server.canonical_admin_unit)


def exercise_effective_weeks(test, con):
    """Same contract executed against SQLite and PostgreSQL."""
    def save(day, token, factor=1, mode="skip", names=("Xã An Thới Đông",)):
        result = commit_weekly_preview(con, {"user_id":1}, preview(day, token, factor, names, lookup=admin_units.unit_lookup(con)), mode, "2026-09-10")
        con.commit()
        return result

    save("2026-08-07", "W32", .5)
    a = save("2026-08-21", "W34-A")
    original = dict(con.execute("SELECT * FROM salt_weekly_records WHERE week_code='2026-W34'").fetchone())
    b = save("2026-08-22", "W34-B-skipped", 9)
    test.assertEqual(b["skipped"], 1)
    test.assertEqual(dict(con.execute("SELECT * FROM salt_weekly_records WHERE week_code='2026-W34'").fetchone()), original)
    raw_b = con.execute("SELECT canonical_data_json FROM salt_weekly_import_rows WHERE batch_id=?", (b["batch_id"],)).fetchone()
    test.assertEqual(json.loads(raw_b[0])["area_land"], 630)
    state = effective_weekly_dashboard(con, batch=str(b["batch_id"]))
    test.assertEqual(state["selected"]["week_code"], "2026-W34")
    test.assertEqual(state["previous"]["week_code"], "2026-W32")
    test.assertEqual(state["rows"][0]["batch_id"], a["batch_id"])
    test.assertEqual(state["rows"][0]["san_luong"], 1000)
    # An earlier report uploaded later must become the comparison, not the current week.
    save("2026-08-14", "W33-A", .7)
    save("2026-08-15", "W33-updated", .8, "update")
    c = save("2026-08-23", "W34-C-updated", 2, "update")
    test.assertEqual(c["updated"], 1)
    state = effective_weekly_dashboard(con, batch=str(b["batch_id"]))
    test.assertEqual([p["week_code"] for p in state["periods"]], ["2026-W34", "2026-W33", "2026-W32"])
    test.assertEqual(state["previous"]["week_code"], "2026-W33")
    test.assertEqual(state["previous_rows"][0]["san_luong"], 800)
    test.assertEqual((state["rows"][0]["area_land"], state["rows"][0]["area_tarp"]), (140, 60))
    test.assertEqual((state["rows"][0]["sold_total"], state["rows"][0]["remaining_total"]), (1000, 1000))
    test.assertEqual((state["rows"][0]["id"], state["rows"][0]["created_at"]), (original["id"], original["created_at"]))
    test.assertEqual(con.execute("SELECT COUNT(*) FROM salt_import_batches").fetchone()[0], 6)
    test.assertEqual(con.execute("SELECT COUNT(*) FROM salt_weekly_import_rows").fetchone()[0], 6)
    # skip is per unit: add a missing unit while preserving the existing unit's winner.
    partial = save("2026-08-21", "W34-partial", 3, names=("Xã An Thới Đông", "Xã Thạnh An"))
    test.assertEqual((partial["inserted"], partial["skipped"]), (1, 1))
    state = effective_weekly_dashboard(con, week="2026-W34")
    test.assertEqual([r["san_luong"] for r in state["rows"]], [2000, 3000])
    unit = effective_weekly_dashboard(con, week="2026-W34", unit_code="27676")
    test.assertIsNone(unit["previous"])
    test.assertEqual(len(unit["rows"]), 1)
    test.assertIsNone(effective_weekly_dashboard(con, unit_code="unknown"))
    test.assertEqual(effective_weekly_dashboard(con, batch="invalid")["selected"]["week_code"], "2026-W34")


class WeeklyFoundationTests(unittest.TestCase):
    setUp = integration.IntegrationTests.setUp
    tearDown = integration.IntegrationTests.tearDown
    db = integration.IntegrationTests.db
    row = integration.IntegrationTests.row
    create_ocop = integration.IntegrationTests.create_ocop

    def test_effective_skip_update_previous_distinct_week_and_unit_scope(self):
        with closing(self.db()) as con:
            exercise_effective_weeks(self, con)
        status, _, response = self.admin.request("GET", "/dashboard?week=2026-W34")
        body = response.decode()
        self.assertEqual(status, 200)
        self.assertIn("So sánh với: 2026-W33", body)
        self.assertIn('class="metric-number">5.000</div>', body)
        self.assertEqual(body.count('<option value="2026-W34"'), 1)
        unit_body = self.b.request("GET", "/dashboard?week=2026-W34")[2].decode()
        self.assertIn("Chưa có tuần trước để so sánh", unit_body)
        self.assertNotIn("Xã An Thới Đông", unit_body)

    def test_skipped_batch_never_replaces_dashboard_or_warning_count(self):
        with closing(self.db()) as con:
            a = preview("2026-08-21", "A")
            commit_weekly_preview(con, {"user_id":1}, a, "skip", "A")
            b = preview("2026-08-22", "B", 9)
            b["rows"][0]["status"] = "warning"
            b["rows"][0]["warnings"] = ["A warning on skipped input"]
            b["warning_rows"] = 1
            result = commit_weekly_preview(con, {"user_id":1}, b, "skip", "B")
            con.commit()
            self.assertEqual(effective_weekly_dashboard(con)["warning_rows"], 0)
        body = self.admin.request("GET", f'/dashboard?batch={result["batch_id"]}')[2].decode()
        self.assertIn('class="metric-number">1.000</div>', body)
        self.assertNotIn('class="metric-number">9.000</div>', body)

    def test_old_sqlite_cli_upgrade_twice_preserves_ocop_and_legacy_data_and_serves_dashboard(self):
        self.create_ocop()
        with closing(self.db()) as con:
            con.execute("INSERT INTO records(report_date,unit_name,created_by,area_land,area_tarp,harvest_land,harvest_tarp,status,created_at,updated_at) VALUES('2026-08-21','Xã An Thới Đông',2,70,30,600,400,'approved','date','date')")
            # Only this disposable fixture is downgraded to a pre-weekly database.
            con.execute("DROP VIEW v_dn_sanluongmuoi_weekly_qd5277")
            for table in ("salt_weekly_records", "salt_weekly_import_rows", "salt_import_batches"):
                con.execute("DROP TABLE " + table)
            con.commit()
            tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name<>'sqlite_sequence'")]
            before = {t:[tuple(r) for r in con.execute('SELECT * FROM "' + t + '"')] for t in tables}
        for _ in range(2):
            result = subprocess.run([sys.executable, "-B", str(Path(server.__file__).with_name("migrate_weekly.py")),
                                     "--db", str(self.path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            with closing(self.db()) as con:
                self.assertEqual(before, {t:[tuple(r) for r in con.execute('SELECT * FROM "' + t + '"')] for t in tables})
                self.assertEqual(con.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(self.admin.request("GET", "/dashboard")[0], 200)
            self.assertEqual(self.admin.request("GET", "/salt/weekly")[0], 200)
        with closing(self.db()) as con:
            commit_weekly_preview(con, {"user_id":1}, preview("2026-08-21", "post-upgrade"), "skip", "date")
            con.commit()
        self.assertEqual(self.admin.request("GET", "/dashboard")[0], 200)

    def test_existing_weekly_upgrade_backfills_only_winning_totals_and_is_idempotent(self):
        with closing(self.db()) as con:
            source = preview("2026-08-21", "winning")
            # Preserve reported I/L totals even when they differ from J+K / M+N.
            source["rows"][0]["canonical"].update(sold_total=501, remaining_total=499)
            commit_weekly_preview(con, {"user_id":1}, source, "skip", "date")
            commit_weekly_preview(con, {"user_id":1}, preview("2026-08-22", "skipped", 9), "skip", "date")
            con.execute("ALTER TABLE salt_weekly_records DROP COLUMN sold_total")
            con.execute("ALTER TABLE salt_weekly_records DROP COLUMN remaining_total")
            con.commit()
            before = [dict(r) for r in con.execute("SELECT * FROM salt_weekly_records")]
            raw = [tuple(r) for r in con.execute("SELECT * FROM salt_weekly_import_rows")]
            migrate_weekly.migrate(con)
            migrate_weekly.migrate(con)
            after = [dict(r) for r in con.execute("SELECT * FROM salt_weekly_records")]
            self.assertEqual(after, [{**before[0], "sold_total":501, "remaining_total":499}])
            self.assertEqual(raw, [tuple(r) for r in con.execute("SELECT * FROM salt_weekly_import_rows")])

    def test_standard_repair_aggregates_once_preserves_details_and_unrelated_methods(self):
        with closing(self.db()) as con:
            con.execute("INSERT INTO records(report_date,unit_name,created_by,area_land,area_tarp,harvest_land,harvest_tarp,sold_land,sold_tarp,remaining_land,remaining_tarp,price_land,price_tarp,damage_land,damage_tarp,status,created_at,updated_at) VALUES('2026-08-21','Xã An Thới Đông',2,70,30,600,400,300,200,300,200,'1.000 - 1.500','2.000',6,4,'approved','date','date')")
            record = con.execute("SELECT * FROM records").fetchone()
            con.execute("INSERT INTO DM_KhoangThoiGian(Ma_ThoiGian,Nam,Thang) VALUES('2026-08',2026,8)")
            for method, area, harvest in (("Truyền thống",70,600),("Trải bạt",30,400),("Công nghiệp",5,50)):
                con.execute("INSERT INTO DN_SanLuongMuoi(Ma_DonViHanhChinh,Ma_ThoiGian,PhuongPhapSX,DienTich,SanLuong) VALUES('27673','2026-08',?,?,?)", (method,area,harvest))
            for _ in range(2):
                server.sync_standard_salt_record(con, record)
            self.assertEqual(dict(record), dict(con.execute("SELECT * FROM records").fetchone()))
            rows = {r["PhuongPhapSX"]:(r["DienTich"],r["SanLuong"]) for r in con.execute("SELECT * FROM DN_SanLuongMuoi")}
            self.assertEqual(rows, {"Truyền thống":(100,1000), "Công nghiệp":(5,50)})

    def test_failed_weekly_upgrade_rolls_back_ddl_without_changing_source(self):
        with closing(self.db()) as con:
            commit_weekly_preview(con, {"user_id":1}, preview("2026-08-21", "raw"), "skip", "date")
            con.execute("ALTER TABLE salt_weekly_records DROP COLUMN sold_total")
            con.execute("ALTER TABLE salt_weekly_records DROP COLUMN remaining_total")
            con.execute("UPDATE salt_weekly_import_rows SET canonical_data_json='invalid-json'")
            con.commit()
            before = [tuple(r) for r in con.execute("SELECT * FROM salt_weekly_records")]
            schema = con.execute("SELECT sql FROM sqlite_master WHERE name='salt_weekly_records'").fetchone()[0]
            with self.assertRaises(json.JSONDecodeError):
                migrate_weekly.migrate(con)
            self.assertEqual(schema, con.execute("SELECT sql FROM sqlite_master WHERE name='salt_weekly_records'").fetchone()[0])
            self.assertEqual(before, [tuple(r) for r in con.execute("SELECT * FROM salt_weekly_records")])

    def test_cli_refuses_non_test_database_without_writing(self):
        path = Path(self.temp.name) / "salt_management.db"
        with closing(self.db()) as source, closing(sqlite3.connect(path)) as target:
            source.backup(target)
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        result = subprocess.run([sys.executable, "-B", str(Path(server.__file__).with_name("migrate_weekly.py")),
                                 "--db", str(path)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Chi chap nhan database *_TEST.db", result.stderr)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)

    def test_weekly_view_uses_detail_sum_keeps_all_details_and_source_totals(self):
        with closing(self.db()) as con:
            data = preview("2026-08-21", "mismatching-totals")
            data["rows"][0]["canonical"].update(dien_tich=999, san_luong=9999)
            before = deepcopy(data)
            commit_weekly_preview(con, {"user_id":1}, data, "skip", "date")
            self.assertEqual(data, before)
            row = con.execute("SELECT * FROM salt_weekly_records").fetchone()
            canonical = data["rows"][0]["canonical"]
            for prefix in ("area", "harvest", "sold", "remaining", "price", "damage"):
                for suffix in ("land", "tarp"):
                    self.assertEqual(row[prefix + "_" + suffix], canonical[prefix + "_" + suffix])
            view = con.execute("SELECT * FROM v_dn_sanluongmuoi_weekly_qd5277").fetchall()
            self.assertEqual(len(view), 1)
            self.assertEqual((view[0]["PhuongPhapSX"], view[0]["DienTich"], view[0]["SanLuong"]), ("Truyền thống",100,1000))
            self.assertEqual((row["dien_tich"], row["san_luong"]), (999,9999))
            self.assertEqual(con.execute("SELECT COUNT(*) FROM DN_SanLuongMuoi").fetchone()[0], 0)


class SaltSumTests(unittest.TestCase):
    def test_totals_never_override_details_and_input_is_unchanged(self):
        record = {"area_land":70,"area_tarp":30,"harvest_land":600,"harvest_tarp":400,
                  "area_total":999,"harvest_total":9999,"price_land":"1.000","price_tarp":"2.000"}
        before = deepcopy(record)
        self.assertEqual(list(method_values(record)), [("Truyền thống",100,1000,None)])
        self.assertEqual(record, before)

    def test_invalid_details_do_not_write_or_remove_legacy_rows(self):
        for value in (-1, float("nan"), float("inf")):
            calls = []
            with self.assertRaises(ValueError):
                sync_methods(lambda *args:calls.append(args), "unit", "2026-08",
                             {"area_land":70,"area_tarp":value,"harvest_land":600,"harvest_tarp":400})
            self.assertEqual(calls, [])
