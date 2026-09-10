"""Role and account regression tests over real HTTP and disposable SQLite."""
import hashlib
from pathlib import Path
from contextlib import closing
import sqlite3
import subprocess
import sys
import unittest

import server
import migrate_roles
import ocop_services as svc
from salt_normalization import exact_price
import test_integration as integration
from test_integration import Client, legacy_schema


class RoleAccountTests(unittest.TestCase):
    setUp = integration.IntegrationTests.setUp
    tearDown = integration.IntegrationTests.tearDown
    db = integration.IntegrationTests.db
    row = integration.IntegrationTests.row
    create_ocop = integration.IntegrationTests.create_ocop
    action = integration.IntegrationTests.action

    def staff(self):
        result = self.admin.request('POST','/users/new', {
            'username':'staff_test','password':'Testing-OCOP-2026','role':'staff','unit_name':'Chi cục'})
        self.assertEqual(result[0],303)
        user = self.row("SELECT * FROM users WHERE username='staff_test'")
        self.assertEqual(user['role'],'staff')
        return Client(self.http.server_address[1]).login('staff_test'), user['id']

    def report(self, client, day='2026-08-20'):
        status, headers, body = client.request('POST','/records/new', {
            'report_date':day,'area_land':'2','area_tarp':'3','harvest_land':'10',
            'harvest_tarp':'20','price_land':'1.200','price_tarp':'2.000 - 2.500'})
        self.assertEqual(status,303,body.decode())
        return int(headers['Location'].split('/')[-1])

    def test_users_pages_and_all_account_writes_are_admin_only(self):
        staff,_ = self.staff()
        self.assertEqual(self.admin.request('GET','/users')[0],200)
        before = self.row('SELECT COUNT(*) n FROM users')
        for client in (staff,self.a):
            for path in ('/users','/users/2/edit','/ocop/access'):
                self.assertEqual(client.request('GET',path)[0],403,path)
            for path in ('/users/new','/users/2/edit','/users/2/delete',
                         '/users/2/activate','/users/2/deactivate','/ocop/access'):
                self.assertEqual(client.request('POST',path,{'role':'admin','active':'1'})[0],403,path)
        self.assertEqual(self.row('SELECT COUNT(*) n FROM users'),before)
        self.assertEqual(self.row('SELECT active FROM users WHERE id=2')['active'],1)

    def test_staff_global_scope_and_unit_isolation(self):
        staff,_ = self.staff()
        rid_a,rid_b = self.report(self.a),self.report(self.b)
        for rid in (rid_a,rid_b):
            self.assertEqual(staff.request('GET',f'/records/{rid}')[0],200)
        self.assertIn(self.a.request('GET',f'/records/{rid_b}')[0],(403,404))
        body = self.a.request('GET','/records?unit=X')[2].decode()
        self.assertNotIn(f'href="/records/{rid_b}"',body)
        self.assertEqual(staff.request('GET','/standard-data')[0],200)
        self.assertIn('Chuyên viên Chi cục',staff.request('GET','/dashboard')[2].decode())
        self.assertNotIn('href="/users"',staff.request('GET','/dashboard')[2].decode())

    def test_staff_return_approve_and_method_upserts(self):
        staff,_ = self.staff()
        rid = self.report(self.a)
        self.assertEqual(self.a.request('POST',f'/records/{rid}/submit',{})[0],303)
        self.assertEqual(staff.request('POST',f'/records/{rid}/return',{'reviewer_note':'Bổ sung'})[0],303)
        self.assertEqual(self.a.request('POST',f'/records/{rid}/submit',{})[0],303)
        self.assertEqual(staff.request('POST',f'/records/{rid}/approve',{})[0],303)
        with closing(self.db()) as con:
            record = con.execute('SELECT * FROM records WHERE id=?',(rid,)).fetchone()
            before = [tuple(r) for r in con.execute('SELECT * FROM DN_SanLuongMuoi ORDER BY PhuongPhapSX')]
            server.sync_standard_salt_record(con,record)
            server.sync_standard_salt_record(con,record)
            after = [tuple(r) for r in con.execute('SELECT * FROM DN_SanLuongMuoi ORDER BY PhuongPhapSX')]
            self.assertEqual(before,after)
            rows = {r['PhuongPhapSX']:dict(r) for r in con.execute('SELECT * FROM DN_SanLuongMuoi')}
            self.assertEqual((rows['Truyền thống']['DienTich'],rows['Truyền thống']['SanLuong'],rows['Truyền thống']['GiaBanBinhQuan']),(2,10,1200))
            self.assertEqual((rows['Trải bạt']['DienTich'],rows['Trải bạt']['SanLuong'],rows['Trải bạt']['GiaBanBinhQuan']),(3,20,0))
            con.execute("UPDATE records SET area_tarp=0,harvest_tarp=0,price_tarp='' WHERE id=?",(rid,))
            server.sync_standard_salt_record(con,record)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM DN_SanLuongMuoi').fetchone()[0],1)

    def test_activation_preserves_profile_and_invalidates_all_sessions(self):
        staff,staff_id = self.staff()
        for uid,client in ((2,self.a),(staff_id,staff)):
            username = self.row('SELECT username FROM users WHERE id=?',(uid,))['username']
            second = Client(self.http.server_address[1]).login(username)
            before = self.row('SELECT * FROM users WHERE id=?',(uid,))
            self.assertEqual(self.admin.request('POST',f'/users/{uid}/deactivate',{})[0],303)
            self.assertFalse(any(s['user_id']==uid for s in server.SESSIONS.values()))
            for c in (client,second):
                self.assertEqual(c.request('GET','/dashboard')[0],303)
            after = self.row('SELECT * FROM users WHERE id=?',(uid,))
            self.assertEqual(after,{**before,'active':0})
            self.assertEqual(self.admin.request('POST',f'/users/{uid}/activate',{})[0],303)
            self.assertEqual(self.row('SELECT * FROM users WHERE id=?',(uid,)),before)
            Client(self.http.server_address[1]).login(username)

    def test_inactive_login_message_requires_correct_password(self):
        self.admin.request('POST','/users/2/deactivate',{})
        client = Client(self.http.server_address[1])
        for username,password,message in (
            ('unit_a','Testing-OCOP-2026','Tài khoản không hoạt động. Vui lòng liên hệ Chi cục để được xử lý.'),
            ('unit_a','wrong','Tên đăng nhập hoặc mật khẩu không đúng.'),
            ('missing','Testing-OCOP-2026','Tên đăng nhập hoặc mật khẩu không đúng.')):
            status,headers,body = client.request('POST','/login',{'username':username,'password':password})
            self.assertEqual(status,401)
            self.assertNotIn('Set-Cookie',headers)
            self.assertIn(message,body.decode())
            if password=='wrong': self.assertNotIn('Tài khoản không hoạt động',body.decode())

    def test_admin_cannot_disable_demote_or_delete_self(self):
        self.assertEqual(self.admin.request('POST','/users/1/deactivate',{})[0],400)
        self.assertEqual(self.admin.request('POST','/users/1/edit',{
            'username':'admin_test','role':'staff','unit_name':'Chi cục'})[0],400)
        self.admin.request('POST','/users/1/delete',{})
        self.assertEqual(self.row('SELECT active,role FROM users WHERE id=1'),{'active':1,'role':'admin'})

    def test_edit_form_staff_and_session_revocation(self):
        staff,uid = self.staff()
        self.assertIn('value="staff" selected',self.admin.request('GET',f'/users/{uid}/edit')[2].decode())
        self.admin.request('POST',f'/users/{uid}/edit',{'username':'staff_test','role':'unit','active':'1','unit_name':'Xã Thạnh An'})
        self.assertFalse(any(s['user_id']==uid for s in server.SESSIONS.values()))
        self.assertEqual(staff.request('GET','/dashboard')[0],303)

    def test_staff_ocop_workflow_and_phase_two_catalog(self):
        staff,_ = self.staff()
        _,_,aid = self.create_ocop(self.a)
        self.assertEqual(staff.request('GET',f'/ocop/applications/{aid}')[0],200)
        self.assertEqual(self.action(self.a,aid,'submit')[0],303)
        self.assertEqual(self.action(staff,aid,'start-review')[0],303)
        self.assertEqual(self.action(staff,aid,'eligible')[0],303)
        self.assertEqual(self.row('SELECT COUNT(*) n FROM ocop_criteria_sets')['n'],26)
        self.assertEqual(self.row('SELECT COUNT(*) n FROM ocop_criteria')['n'],78)
        self.assertEqual(self.row('SELECT COUNT(*) n FROM PTNT_OCOP')['n'],0)
        self.assertEqual(staff.request('GET','/ocop/criteria')[0],200)

    def test_dropdown_active_routes_and_footer(self):
        for route,group in (('/records','salt'),('/ocop/products','ocop')):
            body=self.admin.request('GET',route)[2].decode()
            self.assertIn(f'data-group="{group}" data-active="true" open',body)
            self.assertIn(f'href="{route}"',body)
            self.assertIn('aria-current="page"',body)
            self.assertIn('<span>TRUNG TÂM CHUYỂN ĐỔI SỐ</span><span>NÔNG NGHIỆP VÀ MÔI TRƯỜNG</span>',body)


class RoleMigrationTests(unittest.TestCase):
    def test_sqlite_migration_failure_rolls_back_and_restores_fk_setting(self):
        con=sqlite3.connect(':memory:');self.addCleanup(con.close)
        con.execute('PRAGMA foreign_keys=ON')
        con.executescript(legacy_schema().replace("'admin','staff','unit'","'admin','unit'"))
        con.execute("INSERT INTO users VALUES(1,'a','hash','admin','CC',1,'date')");con.commit()
        before=con.serialize()
        def deny_drop(action,*args):
            return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_DROP_TABLE else sqlite3.SQLITE_OK
        con.set_authorizer(deny_drop)
        with self.assertRaises(sqlite3.DatabaseError): migrate_roles.migrate(con)
        con.set_authorizer(None)
        self.assertEqual(con.serialize(),before)
        self.assertEqual(con.execute('PRAGMA foreign_keys').fetchone()[0],1)

    def test_sqlite_rebuild_preserves_rows_fks_indexes_triggers_and_sequence(self):
        con=sqlite3.connect(':memory:'); self.addCleanup(con.close)
        con.execute('PRAGMA foreign_keys=ON')
        con.executescript(legacy_schema().replace("'admin','staff','unit'","'admin','unit'"))
        con.execute("INSERT INTO users VALUES(1,'a','hash','admin','CC',1,'date')")
        con.execute("INSERT INTO audit_logs(record_id,user_id,action,detail,created_at) VALUES(NULL,1,'old','history','date')")
        con.execute('CREATE INDEX preserve_username ON users(username)')
        con.execute("CREATE TRIGGER preserve_trigger AFTER UPDATE ON users BEGIN SELECT 1; END")
        con.execute('CREATE VIEW user_view AS SELECT username FROM users')
        con.execute("UPDATE sqlite_sequence SET seq=50 WHERE name='users'")
        con.commit()
        before=con.execute('SELECT * FROM users').fetchall()
        self.assertTrue(migrate_roles.migrate(con))
        self.assertEqual(con.execute('SELECT * FROM users').fetchall(),before)
        self.assertEqual(con.execute('SELECT COUNT(*) FROM audit_logs').fetchone()[0],1)
        self.assertEqual(con.execute('PRAGMA foreign_key_check').fetchall(),[])
        self.assertEqual(con.execute('SELECT * FROM user_view').fetchall(),[('a',)])
        snapshot=con.serialize(); self.assertFalse(migrate_roles.migrate(con)); self.assertEqual(snapshot,con.serialize())
        con.execute("INSERT INTO users(username,password_hash,role,unit_name,created_at) VALUES('s','h','staff','CC','date')")
        self.assertEqual(con.execute("SELECT id FROM users WHERE username='s'").fetchone()[0],51)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM sqlite_master WHERE name IN ('preserve_username','preserve_trigger')").fetchone()[0],2)

    def test_sqlite_runtime_imports_without_postgres_dependencies(self):
        code = """import sys
class Block:
 def find_spec(self,name,*args):
  if name.split('.')[0] in ('psycopg','dotenv'): raise ImportError(name)
sys.meta_path.insert(0,Block())
import server, ocop_services, ocop_pages, migrate_roles
server.DB_PATH='isolated_TEST.db'
assert not server.using_postgres()
"""
        result=subprocess.run([sys.executable,'-B','-c',code],cwd=Path(server.__file__).parent,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_prices_are_not_inferred_from_ranges_or_ambiguous_text(self):
        for value in ('1.000 - 1.500','1,000','từ 1000','1e3',float('inf'),-1):
            self.assertIsNone(exact_price(value),value)
        self.assertEqual(exact_price('1.200'),1200)
        self.assertEqual(exact_price('1200,50'),1200.5)
