"""HTTP regression checks against disposable TEST databases, never production."""
import ast
import hashlib
import http.client
import io
from pathlib import Path
import re
import sqlite3
import tempfile
import threading
import unittest
from urllib.parse import urlencode

import server
import ocop_db


def legacy_schema():
    tree = ast.parse(Path(server.__file__).read_text(encoding="utf-8"))
    init = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "init_db")
    return next(n.args[0].value for n in ast.walk(init)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "executescript")


class Client:
    def __init__(self, port):
        self.port, self.cookie, self.csrf = port, "", ""

    def request(self, method, path, data=None, csrf=True, content_type=None):
        headers = {"Cookie": self.cookie}
        body = None
        if data is not None:
            if isinstance(data, dict):
                data = dict(data)
                if csrf:
                    data.setdefault("csrf", self.csrf)
                body = urlencode(data).encode()
                headers["Content-Type"] = "application/x-www-form-urlencoded"
            else:
                body = data
            if content_type:
                headers["Content-Type"] = content_type
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        connection.request(method, path, body, headers)
        response = connection.getresponse()
        payload, result_headers = response.read(), dict(response.getheaders())
        status = response.status
        if "Set-Cookie" in result_headers:
            self.cookie = result_headers["Set-Cookie"].split(";", 1)[0]
        connection.close()
        return status, result_headers, payload

    def login(self, username, password="Testing-OCOP-2026"):
        status, _, _ = self.request("POST", "/login", {"username":username,"password":password}, csrf=False)
        if status != 303:
            raise AssertionError(f"Login failed: {status}")
        _, _, body = self.request("GET", "/records/new")
        self.csrf = re.search(rb'name="csrf" value="([^"]+)"', body).group(1).decode()
        return self


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ocop-regression-")
        self.path = Path(self.temp.name) / "integration_TEST.db"
        self.old_path = server.DB_PATH
        server.DB_PATH = str(self.path)
        with server.SESSION_LOCK:
            server.SESSIONS.clear()
        con = self.db()
        con.executescript(legacy_schema())
        password = server.hash_password("Testing-OCOP-2026")
        for uid, username, role, name in ((1,"admin_test","admin","Chi cục"),
                (2,"unit_a","unit","Xã An Thới Đông"),(3,"unit_b","unit","Xã Thạnh An"),
                (4,"unmapped","unit","Đơn vị chưa có mã")):
            con.execute("INSERT INTO users VALUES(?,?,?,?,?,1,?)",(uid,username,password,role,name,server.now_text()))
        for code,name in (("27673","Xã An Thới Đông"),("27676","Xã Thạnh An")):
            con.execute("INSERT INTO DM_DonViHanhChinh VALUES(?,NULL,?,'xa',1)",(code,name))
        con.commit()
        ocop_db.migrate(con)
        con.commit()
        con.close()
        class QuietHandler(server.Handler):
            def log_message(self, *args):
                pass
        self.http = server.ThreadingHTTPServer(("127.0.0.1",0),QuietHandler)
        self.thread = threading.Thread(target=self.http.serve_forever,daemon=True)
        self.thread.start()
        port = self.http.server_address[1]
        self.admin = Client(port).login("admin_test")
        self.a = Client(port).login("unit_a")
        self.b = Client(port).login("unit_b")

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=5)
        server.DB_PATH = self.old_path
        self.temp.cleanup()

    def db(self):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        return con

    def row(self, sql, args=()):
        con = self.db()
        try:
            row = con.execute(sql,args).fetchone()
            return dict(row) if row else None
        finally:
            con.close()

    def create_ocop(self, client=None, code="27673", name="Muối sạch thử nghiệm"):
        client = client or self.a
        status, headers, body = client.request("POST", "/ocop/entities/new", {
            "name":"HTX thử nghiệm", "facility_type":"Hợp tác xã", "address":"Địa chỉ thử nghiệm",
            "ma_don_vi_hanh_chinh":code, "representative_name":"Đại diện thử nghiệm", "phone":"0900000000"})
        self.assertEqual(status,303,body.decode())
        entity_id = int(headers["Location"].rsplit("/",1)[1])
        entity = self.row("SELECT * FROM ocop_entities WHERE id=?",(entity_id,))
        criteria_id = self.row("SELECT id FROM ocop_criteria_sets WHERE code='QD26-10'")["id"]
        status, headers, body = client.request("POST","/ocop/products/new",{
            "name":name,"ma_co_so":entity["ma_co_so"],"criteria_set_id":criteria_id, "description":"Sản phẩm thử"})
        self.assertEqual(status,303,body.decode())
        pid = int(headers["Location"].rsplit("/",1)[1])
        status, headers, body = client.request("POST","/ocop/applications/new",{
            "product_id":pid,"evaluation_type":"new","year":"2026"})
        self.assertEqual(status,303,body.decode())
        aid = int(headers["Location"].rsplit("/",1)[1])
        return entity_id,pid,aid

    def action(self, client, aid, action, **extra):
        row=self.row("SELECT * FROM ocop_applications WHERE id=?",(aid,))
        return client.request("POST",f"/ocop/applications/{aid}/{action}",{"revision":row["revision"], **extra})

    def test_ocop_workflow_scope_snapshot_and_audit(self):
        eid,pid,aid=self.create_ocop()
        for route in ("/ocop", "/ocop/entities", "/ocop/products", "/ocop/applications",
                "/ocop/criteria", "/ocop/criteria/10",
                f"/ocop/entities/{eid}",f"/ocop/products/{pid}",f"/ocop/applications/{aid}"):
            self.assertEqual(self.a.request("GET",route)[0],200,route)
        self.assertIn(self.b.request("GET",f"/ocop/applications/{aid}")[0],(403,404))
        self.assertNotIn("Muối sạch thử nghiệm".encode(), self.b.request("GET","/ocop/products?unit=27673")[2])
        self.assertIn(self.action(self.b,aid,"submit")[0],(403,404))
        product = self.row("SELECT * FROM ocop_products WHERE id=?", (pid,))
        application = self.row("SELECT * FROM ocop_applications WHERE id=?", (aid,))
        criteria = self.row("SELECT * FROM ocop_criteria_sets WHERE code='QD26-10'")
        self.assertEqual(product["criteria_set_id"], criteria["id"])
        self.assertEqual(application["criteria_set_id"], criteria["id"])
        self.assertEqual(product["product_group"], "Gia vị")
        self.assertEqual(self.action(self.a,aid,"submit")[0],303)
        application=self.row("SELECT * FROM ocop_applications WHERE id=?",(aid,))
        self.assertEqual(application["status"],"submitted")
        self.assertIn("Muối sạch thử nghiệm",application["submission_snapshot_json"])
        self.assertIn(self.a.request("POST",f"/ocop/applications/{aid}/edit",{
            "product_id":pid,"evaluation_type":"new","year":"2027","revision":application["revision"]})[0],(400,403,409))
        self.assertIn(self.action(self.a,aid,"eligible")[0],(400,403))
        self.assertEqual(self.action(self.admin,aid,"start-review")[0],303)
        self.assertEqual(self.action(self.admin,aid,"return",comment="")[0],400)
        self.assertEqual(self.action(self.admin,aid,"return",comment="Bổ sung thông tin chủ thể")[0],303)
        self.assertEqual(self.action(self.a,aid,"submit")[0],303)
        self.assertEqual(self.action(self.admin,aid,"eligible")[0],303)
        self.assertEqual(self.row("SELECT status FROM ocop_applications WHERE id=?",(aid,))["status"],"eligible")
        self.assertEqual(self.row("SELECT COUNT(*) AS n FROM PTNT_OCOP")["n"],0)
        self.assertGreaterEqual(self.row("SELECT COUNT(*) AS n FROM ocop_reviews WHERE application_id=?",(aid,))["n"],6)
        self.assertEqual(self.row("SELECT COUNT(*) AS n FROM audit_logs WHERE module='ocop' AND record_id IS NOT NULL")["n"],0)
        self.assertGreaterEqual(self.row("SELECT COUNT(*) AS n FROM audit_logs WHERE module='ocop'")["n"],8)

    def test_crud_archival_concurrency_and_input_safety(self):
        eid,pid,aid=self.create_ocop(name='<script>alert("x")</script>')
        response=self.a.request("GET",f"/ocop/products/{pid}")
        self.assertNotIn(b'<script>alert("x")</script>',response[2])
        app=self.row("SELECT * FROM ocop_applications WHERE id=?",(aid,))
        data={"product_id":pid,"evaluation_type":"upgrade","year":"2027","revision":app["revision"]}
        self.assertEqual(self.a.request("POST",f"/ocop/applications/{aid}/edit",data)[0],303)
        self.assertEqual(self.a.request("POST",f"/ocop/applications/{aid}/edit",data)[0],409)
        self.assertEqual(self.a.request("POST","/ocop/applications/new",{"product_id":pid,"evaluation_type":"new","year":"2026"})[0],409)
        self.assertEqual(self.action(self.a,aid,"cancel")[0],303)
        product=self.row("SELECT * FROM ocop_products WHERE id=?",(pid,))
        self.assertEqual(self.a.request("POST",f"/ocop/products/{pid}/archive",{"updated_at":product["updated_at"]})[0],303)
        self.assertEqual(self.row("SELECT status FROM ocop_products WHERE id=?",(pid,))["status"],"archived")
        self.assertIsNotNone(self.row("SELECT * FROM ocop_applications WHERE id=?",(aid,)))
        self.assertEqual(self.a.request("POST","/ocop/entities/new",{"name":"","facility_type":"Hợp tác xã","ma_don_vi_hanh_chinh":"27673"})[0],400)
        self.assertEqual(self.a.request("POST","/ocop/entities/new",{"name":"Tên được giữ","facility_type":"Hợp tác xã","ma_don_vi_hanh_chinh":"27673","email":"invalid"})[0],400)
        self.assertIn("Tên được giữ".encode(),self.a.request("POST","/ocop/entities/new",{"name":"Tên được giữ","facility_type":"Hợp tác xã","ma_don_vi_hanh_chinh":"27673","email":"invalid"})[2])

    def test_security_filters_csrf_mapping_and_disabled_session(self):
        self.create_ocop()
        self.assertEqual(self.a.request("POST","/ocop/entities/new",{},csrf=False)[0],400)
        # The server must reject the declared size without waiting for a body.
        oversized=http.client.HTTPConnection("127.0.0.1",self.http.server_address[1],timeout=5)
        oversized.putrequest("POST","/ocop/entities/new")
        oversized.putheader("Content-Type","application/x-www-form-urlencoded")
        oversized.putheader("Content-Length",str(256*1024+1))
        oversized.endheaders()
        response=oversized.getresponse()
        self.assertEqual(response.status,413)
        response.read();oversized.close()
        self.assertEqual(self.a.request("POST","/ocop/entities/new",b"file",content_type="multipart/form-data; boundary=x")[0],415)
        unknown=Client(self.http.server_address[1]).login("unmapped")
        self.assertEqual(unknown.request("GET","/ocop")[0],403)
        self.assertEqual(self.a.request("GET","/ocop/access")[0],403)
        self.assertEqual(self.admin.request("GET","/ocop/access")[0],200)
        self.assertEqual(self.admin.request("POST","/ocop/access",{"user_id":4,"unit_code":"27676"})[0],303)
        unknown.login("unmapped")
        self.assertEqual(unknown.request("GET","/ocop")[0],200)
        self.assertNotIn("Muối sạch thử nghiệm".encode(),unknown.request("GET","/ocop/products")[2])
        with self.db() as con:
            con.execute("UPDATE users SET active=0 WHERE id=2")
        con.close()
        self.assertEqual(self.a.request("GET","/ocop")[0],303)

    def test_entity_product_edit_forms_and_lock_after_submission(self):
        eid,pid,aid=self.create_ocop()
        for route in ("/ocop/entities/new","/ocop/products/new","/ocop/applications/new",
                f"/ocop/entities/{eid}/edit",f"/ocop/products/{pid}/edit",f"/ocop/applications/{aid}/edit"):
            status,_,body=self.a.request("GET",route)
            self.assertEqual(status,200,body.decode())
            self.assertIn(b'name="csrf"',body)
        entity=self.row("SELECT * FROM ocop_entities WHERE id=?",(eid,))
        entity_data={"name":"HTX đã chỉnh sửa","facility_type":"Hợp tác xã","address":"Địa chỉ mới",
                     "ma_don_vi_hanh_chinh":"27673","updated_at":entity["updated_at"]}
        self.assertEqual(self.a.request("POST",f"/ocop/entities/{eid}/edit",entity_data)[0],303)
        self.assertEqual(self.a.request("POST",f"/ocop/entities/{eid}/edit",entity_data)[0],409)
        product=self.row("SELECT * FROM ocop_products WHERE id=?",(pid,))
        product_data={"name":"Muối đã chỉnh sửa","ma_co_so":product["ma_co_so"],"criteria_set_id":product["criteria_set_id"],
                      "description":"Đã bổ sung","updated_at":product["updated_at"],"current_star":"5","status":"completed"}
        self.assertEqual(self.a.request("POST",f"/ocop/products/{pid}/edit",product_data)[0],303)
        product=self.row("SELECT * FROM ocop_products WHERE id=?",(pid,))
        self.assertEqual(product["ten_san_pham"],"Muối đã chỉnh sửa")
        self.assertIsNone(product["current_star"])
        self.assertEqual(product["status"],"active")
        self.assertEqual(self.row("SELECT TenSanPham FROM DM_SanPham WHERE Ma_SanPham=?",(product["ma_san_pham"],))["TenSanPham"],"Muối đã chỉnh sửa")
        self.assertEqual(self.action(self.a,aid,"submit")[0],303)
        self.assertEqual(self.a.request("POST",f"/ocop/products/{pid}/edit",{**product_data,"updated_at":product["updated_at"]})[0],409)
        self.assertEqual(self.action(self.admin,aid,"return",comment="Bổ sung mô tả")[0],303)
        self.assertEqual(self.a.request("POST",f"/ocop/products/{pid}/edit",{**product_data,"updated_at":product["updated_at"]})[0],303)
        self.assertEqual(self.a.request("POST","/ocop/entities/new",{**entity_data,"ma_don_vi_hanh_chinh":"27676"})[0],403)

    def test_transaction_rollback_and_revoked_admin_assignment(self):
        import ocop_services as svc
        con=self.db()
        con.execute("CREATE TRIGGER fail_ocop_audit BEFORE INSERT ON audit_logs WHEN NEW.module='ocop' BEGIN SELECT RAISE(ABORT, 'test failure'); END")
        con.commit();con.close()
        response=self.a.request("POST","/ocop/entities/new",{"name":"Rollback","facility_type":"Hộ gia đình","address":"Test","ma_don_vi_hanh_chinh":"27673"})
        self.assertEqual(response[0],409)
        self.assertEqual(self.row("SELECT COUNT(*) AS n FROM ocop_entities")["n"],0)
        self.assertEqual(self.row("SELECT COUNT(*) AS n FROM DM_CoSo")["n"],0)
        con=self.db()
        con.execute("DROP TRIGGER fail_ocop_audit")
        con.execute("UPDATE users SET active=0 WHERE id=1")
        con.commit()
        with self.assertRaises(svc.OcopError):
            server.save_ocop_access(con,{"user_id":1,"role":"admin"},{"user_id":4,"unit_code":"27673"})
        self.assertEqual(con.execute("SELECT COUNT(*) FROM user_admin_units WHERE user_id=4").fetchone()[0],0)
        con.close()

    def test_dashboard_filters_pagination_and_selector_over_200(self):
        self.create_ocop()
        self.create_ocop(self.b,"27676",name="Sản phẩm đơn vị B")
        import ocop_services as svc
        con=self.db()
        admin={"user_id":1,"role":"admin"}
        self.assertEqual(svc.dashboard(con,admin,{"unit":"27673","year":"2026"})["applications"],1)
        self.assertEqual(svc.dashboard(con,admin,{"year":"2025"})["applications"],0)
        self.assertEqual(svc.list_products(con,admin,{"page_size":"1"})["pages"],2)
        self.assertEqual(svc.list_products(con,admin,{"page_size":"1","page":"2"})["page"],2)
        for i in range(205):
            code=f"CHOICE{i:04}"
            con.execute("INSERT INTO DM_CoSo VALUES(?,?,?,?,?)",(code,f"Chủ thể {i:03}","Hộ gia đình","Test","27673"))
            con.execute("INSERT INTO ocop_entities(ma_co_so,created_by,created_at,updated_at) VALUES(?,2,'2026','2026')",(code,))
        con.commit();con.close()
        status,_,body=self.a.request("GET","/ocop/products/new")
        self.assertEqual(status,200,body.decode())
        self.assertIn(b'CHOICE0204',body)
        self.assertNotIn("Sản phẩm đơn vị B".encode(),self.a.request("GET","/ocop/applications/new")[2])

    def test_dynamic_criteria_catalog_and_product_requirement(self):
        for client in (self.admin, self.a):
            status, _, body = client.request("GET", "/ocop/criteria")
            self.assertEqual(status, 200)
            self.assertIn("QD26-10".encode(), body)
            self.assertIn("Gia vị khác (muối, hành, tỏi, tiêu)".encode(), body)
            status, _, body = client.request("GET", "/ocop/criteria/10")
            self.assertEqual(status, 200)
            self.assertIn("40 điểm".encode(), body)
            self.assertIn("25 điểm".encode(), body)
            self.assertIn("35 điểm".encode(), body)
        status, _, body = self.a.request("GET", "/ocop/products/new")
        self.assertEqual(status, 200)
        self.assertEqual(body.count(b'<option value='), 28)  # empty + entity + 26 criteria options
        self.assertIn(b'name="criteria_set_id"', body)
        self.assertNotIn(b'name="product_group"', body)

        status, headers, body = self.a.request("POST", "/ocop/entities/new", {
            "name":"HTX thiếu tiêu chí", "facility_type":"Hợp tác xã", "address":"Test",
            "ma_don_vi_hanh_chinh":"27673"})
        self.assertEqual(status, 303)
        entity_id = int(headers["Location"].rsplit("/",1)[1])
        entity = self.row("SELECT * FROM ocop_entities WHERE id=?", (entity_id,))
        status, _, _ = self.a.request("POST", "/ocop/products/new", {
            "name":"Sản phẩm thiếu tiêu chí", "ma_co_so":entity["ma_co_so"], "description":""})
        self.assertEqual(status, 400)
        self.assertEqual(self.row("SELECT COUNT(*) AS n FROM ocop_products")["n"], 0)
        self.assertEqual(self.a.request("POST", "/ocop/criteria/10", {})[0], 404)

    def test_application_snapshot_freezes_criteria_set(self):
        _eid, pid, aid = self.create_ocop()
        self.assertEqual(self.action(self.a, aid, "submit")[0], 303)
        row = self.row("SELECT * FROM ocop_applications WHERE id=?", (aid,))
        import json
        snapshot = json.loads(row["submission_snapshot_json"])
        self.assertEqual(snapshot["schema_version"], 2)
        self.assertEqual(snapshot["criteria_set"]["code"], "QD26-10")
        self.assertEqual(snapshot["criteria_set"]["legal_document"], "26/2026/QĐ-TTg")

    def test_salt_create_edit_submit_return_approve_and_standard_data(self):
        data={"report_date":"2026-08-15","unit_name":"Xã Thạnh An","area_land":"2","harvest_land":"6",
              "sold_land":"3","remaining_land":"3","households":"2","workers":"4","price_land":"1.000 - 1.500"}
        status,headers,body=self.a.request("POST","/records/new",data)
        self.assertEqual(status,303,body.decode())
        rid=int(headers["Location"].rsplit("/",1)[1])
        row=self.row("SELECT * FROM records WHERE id=?",(rid,))
        self.assertEqual(row["unit_name"],"Xã An Thới Đông")
        self.assertEqual(server.record_totals(row)["avg_yield"],3)
        self.assertIn(self.b.request("GET",f"/records/{rid}")[0],(403,404))
        self.assertEqual(self.a.request("POST",f"/records/{rid}/edit",{**data,"area_land":"3"})[0],303)
        self.assertEqual(self.a.request("POST",f"/records/{rid}/submit",{})[0],303)
        self.assertEqual(self.admin.request("POST",f"/records/{rid}/return",{"reviewer_note":"Kiểm tra số liệu"})[0],303)
        self.assertEqual(self.a.request("POST",f"/records/{rid}/edit",data)[0],303)
        self.assertEqual(self.a.request("POST",f"/records/{rid}/submit",{})[0],303)
        self.assertEqual(self.admin.request("POST",f"/records/{rid}/approve",{})[0],303)
        normalized=self.row("SELECT * FROM DN_SanLuongMuoi WHERE Ma_DonViHanhChinh='27673'")
        self.assertEqual((normalized["DienTich"],normalized["SanLuong"],normalized["GiaBanBinhQuan"]),(2,6,0))
        self.assertEqual(normalized["Ma_ThoiGian"],"2026-08")
        self.assertEqual(self.row("SELECT COUNT(*) AS n FROM DN_SanLuongMuoi")["n"],1)
        for route in ("/dashboard","/records","/standard-data",f"/records/{rid}","/import-excel","/users"):
            self.assertEqual(self.admin.request("GET",route)[0],200,route)
        self.assertEqual(self.a.request("GET","/standard-data")[0],403)
        self.assertEqual(self.a.request("GET","/users")[0],403)
        self.assertEqual(self.a.request("GET","/import-excel")[0],403)

    def test_weekly_excel_preview_commit_lookup_and_no_ocop_side_effects(self):
        from openpyxl import Workbook
        wb=Workbook();ws=wb.active;ws.title="Mau"
        ws.append(["STT","Đơn vị"])
        row=[None]*27
        row[0]=1;row[1]="Xã An Thới Đông";row[2]=3;row[3]=2;row[4]=1;row[5]=15;row[6]=10;row[7]=5
        row[18]=2;row[19]=4;row[20]="1.000 - 1.500";row[21]="2.000"
        ws.append(row)
        row2=list(row);row2[0]=2;row2[1]="Xã Thạnh An";ws.append(row2)
        out=io.BytesIO();wb.save(out)
        boundary="TEST_OCOP_BOUNDARY"
        def upload(client):
            parts=[]
            for key,value in {"csrf":client.csrf,"report_date":"2026-07-01","sheet_name":"Mau"}.items():
                parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="excel_file"; filename="sample.xlsx"\r\nContent-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n'.encode()+out.getvalue()+b'\r\n')
            parts.append(f'--{boundary}--\r\n'.encode())
            return client.request("POST","/import-excel",b''.join(parts),content_type=f"multipart/form-data; boundary={boundary}")
        self.assertEqual(upload(self.a)[0],403)
        status,headers,_=upload(self.admin)
        self.assertEqual((status,headers['Location']),(303,'/import-excel/preview'))
        status,_,body=self.admin.request('GET','/import-excel/preview')
        self.assertEqual(status,200);self.assertIn('2026-W27',body.decode())
        self.assertEqual(self.row("SELECT COUNT(*) AS n FROM salt_weekly_records")["n"],0)
        status,headers,_=self.admin.request('POST','/import-excel/confirm',{'mode':'skip'})
        self.assertEqual(status,303);self.assertIn('/salt/weekly?week=2026-W27',headers['Location'])
        self.assertEqual(self.row("SELECT COUNT(*) AS n FROM salt_weekly_records")["n"],2)
        self.assertEqual(self.row("SELECT COUNT(*) AS n FROM records")["n"],0)
        self.assertEqual(self.row("SELECT COUNT(*) AS n FROM DN_SanLuongMuoi")["n"],0)
        dashboard=self.admin.request('GET','/dashboard')[2].decode()
        self.assertIn('Mau · 2026-W27',dashboard)
        self.assertIn('Chưa có sheet trước để so sánh',dashboard)
        self.assertIn('2</div><div class="status-card-label">Đơn vị trong kỳ',dashboard)
        body=self.admin.request('GET','/salt/weekly?week=2026-W27')[2].decode()
        self.assertIn('1</strong><span>sheet báo cáo',body)
        self.assertIn('Mỗi sheet là một báo cáo',body)
        self.assertIn('class="excel-sheet"',body)
        self.assertIn('Xã An Thới Đông',body)
        self.assertIn('class="salt-tab active" href="/salt/weekly"',body)
        self.assertIn('Tra cứu theo tuần',body)
        unit_body=self.a.request('GET','/salt/weekly?week=2026-W27')[2].decode()
        self.assertIn('Xã An Thới Đông',unit_body);self.assertNotIn('Xã Thạnh An',unit_body)
        self.assertNotIn('Import Excel tuần',unit_body)
        upload(self.admin)
        self.admin.request('POST','/import-excel/confirm',{'mode':'skip'})
        self.assertEqual(self.row("SELECT COUNT(*) AS n FROM salt_import_batches")["n"],1)
        con=self.db()
        salt_before={t:[tuple(r) for r in con.execute('SELECT * FROM '+t)] for t in ('records','DN_SanLuongMuoi','salt_weekly_records')}
        con.close()
        self.create_ocop()
        con=self.db()
        self.assertEqual(salt_before,{t:[tuple(r) for r in con.execute('SELECT * FROM '+t)] for t in salt_before})
        self.assertEqual(con.execute('PRAGMA foreign_key_check').fetchall(),[])
        con.close()

    def test_account_links_password_and_logout(self):
        self.create_ocop()
        self.assertEqual(self.admin.request("POST","/users/2/delete",{})[0],303)
        self.assertEqual(self.row("SELECT active FROM users WHERE id=2")["active"],0)
        self.assertEqual(self.a.request("GET","/records")[0],303)
        self.assertEqual(self.b.request("POST","/change-password",{"old":"Testing-OCOP-2026","new":"New-Testing-2026","new2":"New-Testing-2026"})[0],303)
        self.assertEqual(self.b.request("GET","/ocop")[0],303)
        self.b.login("unit_b","New-Testing-2026")
        self.assertEqual(self.b.request("GET","/logout")[0],303)
        self.assertEqual(self.b.request("GET","/ocop")[0],303)


if __name__ == "__main__":
    unittest.main()
