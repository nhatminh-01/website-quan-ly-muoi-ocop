"""Administrative catalog contracts on disposable databases and real HTTP routes."""
from contextlib import closing
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import unittest

import admin_units
import migrate_admin_units
import ocop_services
import server
import test_integration as integration
from test_integration import Client
from test_weekly_foundation import preview


def upload_weekly(client, name, token):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Tuần"
    ws.append(["STT", "Đơn vị"])
    ws.append([1, name, 100, 70, 30, 1000, 600, 400] + [None] * 18 + [token])
    stream = io.BytesIO()
    wb.save(stream)
    wb.close()
    boundary = "ADMIN_UNIT_FIXTURE"
    parts = []
    for key, value in {"csrf":client.csrf,"report_date":"2026-08-21","sheet_name":"Tuần"}.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="excel_file"; filename="fixture.xlsx"\r\nContent-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n'.encode() + stream.getvalue() + b'\r\n')
    parts.append(f'--{boundary}--\r\n'.encode())
    return client.request("POST","/import-excel",b''.join(parts),content_type=f"multipart/form-data; boundary={boundary}")


def exercise_catalog_http(test, admin, staff, unit, connection):
    """The same account/catalog/import contract runs on SQLite and PostgreSQL."""
    def read(sql):
        with closing(connection()) as con:
            return [dict(row) for row in con.execute(sql).fetchall()]

    for client in (staff, unit):
        for path in ("/admin-units", "/admin-units/new", "/admin-units/27595/edit"):
            test.assertEqual(client.request("GET",path)[0],403,path)
        for path in ("/admin-units/new", "/admin-units/27595/edit", "/admin-units/27595/deactivate", "/admin-units/27595/activate", "/admin-units/27595/delete"):
            test.assertEqual(client.request("POST",path,{})[0],403,path)
    body = admin.request("GET","/admin-units")[2].decode()
    for value in ('href="/admin-units"','placeholder="Tìm báo cáo"','Xã Tân Nhựt','Số tài khoản liên kết'):
        test.assertIn(value,body)
    test.assertNotIn('Tìm báo cáo muối',body)
    test.assertEqual(admin.request("GET","/admin-units/new")[0],200)
    data = {"code":"99001","name":"Xã Kiểm thử danh mục","level":"xa","parent_code":"79","active":"1"}
    test.assertEqual(admin.request("POST","/admin-units/new",data)[0],303)
    test.assertEqual(admin.request("POST","/admin-units/new",data)[0],409)
    test.assertEqual(admin.request("POST","/admin-units/new",{**data,"code":"TMP99001"})[0],400)
    test.assertEqual(admin.request("POST","/admin-units/99001/edit",{**data,"parent_code":"99001"})[0],400)
    test.assertEqual(admin.request("POST","/admin-units/99001/edit",{**data,"name":"Xã Đổi tên thử nghiệm"})[0],303)
    body = admin.request("GET","/admin-units?q=99001&level=xa&active=1")[2].decode()
    test.assertIn("Xã Đổi tên thử nghiệm",body)
    test.assertNotIn("Xã Tân Nhựt",body)
    body = admin.request("GET","/users")[2].decode()
    for value in ('<select name="unit_code" required>','value="27595"','value="99001"'):
        test.assertIn(value,body)
    before = read("SELECT id FROM users ORDER BY id")
    account = {"username":"catalog_unit","password":"Testing-OCOP-2026","role":"unit","unit_code":"27595","unit_name":"Tên tự do giả"}
    test.assertEqual(admin.request("POST","/users/new",{**account,"unit_code":""})[0],400)
    test.assertEqual(read("SELECT id FROM users ORDER BY id"),before)
    test.assertEqual(admin.request("POST","/users/new",account)[0],303)
    row = read("SELECT u.id,u.unit_name,m.ma_don_vi_hanh_chinh AS code FROM users u JOIN user_admin_units m ON m.user_id=u.id WHERE u.username='catalog_unit'")[0]
    test.assertEqual((row["unit_name"],row["code"]),("Xã Tân Nhựt","27595"))
    client = Client(admin.port).login("catalog_unit")
    test.assertEqual(client.request("GET","/ocop")[0],200)
    test.assertEqual(client.request("GET","/ocop/entities/new")[0],200)
    uid = row["id"]
    with closing(connection()) as con:
        test.assertEqual(ocop_services.get_scope(con,{"user_id":uid,"role":"unit"}),"27595")
        # Direct DB addition is visible without editing Python or restarting the server.
        con.execute("INSERT INTO DM_DonViHanhChinh(Ma_DonViHanhChinh,TenDonVi,CapHanhChinh,Ma_DonViCapTren,TinhTrang) VALUES('99002','Xã Thêm trực tiếp','xa','79',TRUE)")
        con.commit()
    for name in ("Xã Tân Nhựt", "Xã Đổi tên thử nghiệm", "Xã Thêm trực tiếp"):
        test.assertEqual(upload_weekly(admin,name,name)[0],303)
        test.assertEqual(admin.request("POST","/import-excel/confirm",{"mode":"skip"})[0],303)
    records = read("SELECT * FROM salt_weekly_records ORDER BY id")
    test.assertEqual({r["ma_don_vi_hanh_chinh"] for r in records},{"27595","99001","99002"})
    test.assertTrue(all((r["area_land"],r["area_tarp"],r["san_luong"]) == (70,30,1000) for r in records))
    raw = read("SELECT * FROM salt_weekly_import_rows ORDER BY id")
    test.assertEqual(upload_weekly(admin,"Xã Thêm trực tiếp","rename-pending")[0],303)
    test.assertEqual(admin.request("POST","/admin-units/99002/edit",{**data,"code":"99002","name":"Xã Đổi tên sau xem trước"})[0],303)
    result = admin.request("POST","/import-excel/confirm",{"mode":"update"})
    test.assertEqual(result[1].get("Location"),"/import-excel/preview")
    test.assertEqual(read("SELECT * FROM salt_weekly_records ORDER BY id"),records)
    test.assertEqual(read("SELECT * FROM salt_weekly_import_rows ORDER BY id"),raw)
    test.assertEqual(client.request("GET","/dashboard")[0],200)
    test.assertEqual(admin.request("POST",f"/users/{uid}/edit",{**account,"unit_code":"99001","active":"1","password":""})[0],303)
    row = read(f"SELECT u.unit_name,m.ma_don_vi_hanh_chinh AS code FROM users u JOIN user_admin_units m ON m.user_id=u.id WHERE u.id={uid}")[0]
    test.assertEqual((row["unit_name"],row["code"]),("Xã Đổi tên thử nghiệm","99001"))
    test.assertEqual(client.request("GET","/ocop")[0],303)
    with closing(connection()) as con:
        test.assertEqual(ocop_services.get_scope(con,{"user_id":uid,"role":"unit"}),"99001")
    logs = read("SELECT detail FROM audit_logs WHERE action='Đổi địa bàn tài khoản' ORDER BY id")
    test.assertEqual((json.loads(logs[-1]["detail"])["before"],json.loads(logs[-1]["detail"])["after"]),("27595","99001"))
    test.assertEqual(upload_weekly(admin,"Xã Đổi tên thử nghiệm","pending")[0],303)
    test.assertEqual(admin.request("POST","/admin-units/99001/deactivate",{})[0],303)
    result = admin.request("POST","/import-excel/confirm",{"mode":"update"})
    test.assertEqual(result[1].get("Location"),"/import-excel/preview")
    test.assertIn("Danh mục hành chính đã thay đổi",admin.request("GET","/import-excel/preview")[2].decode())
    test.assertEqual(admin.request("POST","/admin-units/99001/delete",{})[0],400)
    test.assertEqual(read("SELECT * FROM salt_weekly_records ORDER BY id"),records)
    test.assertEqual(read("SELECT * FROM salt_weekly_import_rows ORDER BY id"),raw)
    test.assertEqual(read(f"SELECT ma_don_vi_hanh_chinh AS code FROM user_admin_units WHERE user_id={uid}")[0]["code"],"99001")
    test.assertNotIn('value="99001"',admin.request("GET","/users")[2].decode())
    test.assertEqual(admin.request("POST","/users/new",{**account,"username":"inactive_unit","unit_code":"99001"})[0],400)
    with closing(connection()) as con:
        test.assertIsNone(admin_units.unit_lookup(con)("Xã Đổi tên thử nghiệm"))
        with test.assertRaises(ocop_services.OcopError):
            ocop_services.get_scope(con,{"user_id":uid,"role":"unit"})
    test.assertEqual(admin.request("POST","/admin-units/99001/activate",{})[0],303)


class AdminUnitTests(unittest.TestCase):
    setUp = integration.IntegrationTests.setUp
    tearDown = integration.IntegrationTests.tearDown
    db = integration.IntegrationTests.db
    row = integration.IntegrationTests.row

    def test_catalog_account_import_and_scope_over_http(self):
        self.assertEqual(self.admin.request("POST","/users/new",{"username":"staff_catalog","password":"Testing-OCOP-2026","role":"staff","unit_name":"Chi cục"})[0],303)
        staff = Client(self.admin.port).login("staff_catalog")
        exercise_catalog_http(self,self.admin,staff,self.a,self.db)

    def test_migration_repeat_preserves_disabled_units_and_business_rows(self):
        with closing(self.db()) as con:
            tables = ("records","salt_weekly_records","ocop_criteria","users")
            before = {table:[tuple(r) for r in con.execute("SELECT * FROM "+table)] for table in tables}
            con.execute("UPDATE DM_DonViHanhChinh SET TenDonVi='Tên do quản trị đặt',TinhTrang=FALSE WHERE Ma_DonViHanhChinh='27595'")
            con.commit()
            for _ in range(2):
                migrate_admin_units.migrate(con)
                self.assertEqual((admin_units.get_unit(con,"27595")["name"],admin_units.get_unit(con,"27595")["active"]),("Tên do quản trị đặt",0))
                self.assertEqual(before,{table:[tuple(r) for r in con.execute("SELECT * FROM "+table)] for table in tables})
            self.assertEqual(con.execute("PRAGMA foreign_key_check").fetchall(),[])

    def test_failed_account_mapping_rolls_back_profile_and_audit(self):
        with closing(self.db()) as con:
            con.execute("CREATE TRIGGER reject_catalog_assignment BEFORE INSERT ON user_admin_units BEGIN SELECT RAISE(ABORT,'fixture failure'); END")
            con.commit()
        before = self.row("SELECT COUNT(*) AS n FROM users")
        response = self.admin.request("POST","/users/new",{"username":"rollback_unit","password":"Testing-OCOP-2026","role":"unit","unit_code":"27595"})
        self.assertEqual(response[0],409)
        self.assertEqual(before,self.row("SELECT COUNT(*) AS n FROM users"))
        self.assertIsNone(self.row("SELECT * FROM users WHERE username='rollback_unit'"))

    def test_failed_mapping_edit_keeps_account_name_and_previous_scope(self):
        with closing(self.db()) as con:
            con.execute("CREATE TRIGGER reject_catalog_change BEFORE UPDATE ON user_admin_units BEGIN SELECT RAISE(ABORT,'fixture failure'); END")
            con.commit()
        user = self.row("SELECT * FROM users WHERE id=2")
        mapping = self.row("SELECT * FROM user_admin_units WHERE user_id=2")
        self.admin.request("POST","/users/2/edit",{"username":"should_rollback","role":"unit","unit_code":"27595","active":"1"})
        self.assertEqual(self.row("SELECT * FROM users WHERE id=2"),user)
        self.assertEqual(self.row("SELECT * FROM user_admin_units WHERE user_id=2"),mapping)

    def test_renaming_catalog_preserves_historical_report_access_and_raw_rows(self):
        response = self.a.request("POST","/records/new",{"report_date":"2026-08-21","area_land":"70","area_tarp":"30","harvest_land":"600","harvest_tarp":"400"})
        self.assertEqual(response[0],303)
        path = response[1]["Location"]
        before = self.row("SELECT * FROM records")
        data = {"code":"27673","name":"Xã Đổi tên danh mục","level":"xa","parent_code":"79","active":"1"}
        self.assertEqual(self.admin.request("POST","/admin-units/27673/edit",data)[0],303)
        self.assertEqual(self.row("SELECT unit_name FROM users WHERE id=2")["unit_name"],data["name"])
        self.assertEqual(self.row("SELECT * FROM records"),before)
        self.assertEqual(self.a.request("GET",path)[0],200)
        self.assertIn(path,self.a.request("GET","/records")[2].decode())
        self.assertIn(self.b.request("GET",path)[0],(403,404))

    def test_migration_cli_adds_tan_nhut_and_refuses_non_test_database(self):
        # This is a disposable fixture, not a supplied user database.
        with closing(self.db()) as con:
            con.execute("DROP TABLE admin_unit_aliases")
            con.execute("DELETE FROM DM_DonViHanhChinh WHERE Ma_DonViHanhChinh='27595'")
            con.commit()
        script = str(Path(server.__file__).with_name("migrate_admin_units.py"))
        for _ in range(2):
            result = subprocess.run([sys.executable,"-B",script,"--db",str(self.path)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(self.row("SELECT TenDonVi AS name,CapHanhChinh AS level,Ma_DonViCapTren AS parent,TinhTrang AS active FROM DM_DonViHanhChinh WHERE Ma_DonViHanhChinh='27595'"),{"name":"Xã Tân Nhựt","level":"xa","parent":"79","active":1})
        target = Path(self.temp.name)/"production_name.db"
        with closing(self.db()) as source, closing(sqlite3.connect(target)) as copy:
            source.backup(copy)
        before = hashlib.sha256(target.read_bytes()).hexdigest()
        result = subprocess.run([sys.executable,"-B",script,"--db",str(target)],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(),before)

    def test_alias_uses_current_database_name_and_no_embedded_tan_nhut_code(self):
        with closing(self.db()) as con:
            self.assertEqual(admin_units.unit_lookup(con)("  XÃ AN THỜI ĐÔNG  "),("Xã An Thới Đông","27673"))
            con.execute("UPDATE DM_DonViHanhChinh SET TenDonVi='Xã Tên trong database' WHERE Ma_DonViHanhChinh='27673'")
            self.assertEqual(admin_units.unit_lookup(con)("Xã An Thời Đông"),("Xã Tên trong database","27673"))
        for file in ("server.py","admin_units.py","weekly_import.py","migrate_admin_units.py"):
            self.assertNotIn('27595',Path(server.__file__).with_name(file).read_text(encoding='utf-8'))
