"""PostgreSQL-only contract and disposable integration checks."""
from copy import deepcopy
import os
from pathlib import Path
import unittest
from uuid import uuid4

import backend_db
import admin_units
from salt_normalization import method_values, sync_methods


ROOT = Path(__file__).resolve().parents[1]


class PostgreSQLContractTests(unittest.TestCase):
    def test_default_configuration_is_repository_postgresql_env(self):
        self.assertEqual(backend_db.default_env_file(), ROOT / "database" / ".env")

    def test_handler_placeholders_are_adapted_for_psycopg(self):
        sql, table = backend_db.translate_sql(
            "INSERT INTO records(unit_name,report_date) VALUES(?,?)"
        )
        self.assertIn("VALUES(%s,%s)", sql)
        self.assertEqual(table, "records")
        self.assertIn("RETURNING id", sql)

    def test_foundations_normalize_to_one_traditional_method(self):
        record = {"area_land": 70, "area_tarp": 30,
                  "harvest_land": 600, "harvest_tarp": 400,
                  "area_total": 999, "harvest_total": 9999}
        before = deepcopy(record)
        self.assertEqual(list(method_values(record)),
                         [("Truyền thống", 100, 1000, None)])
        self.assertEqual(record, before)

    def test_invalid_foundation_never_writes(self):
        calls = []
        with self.assertRaises(ValueError):
            sync_methods(lambda *args: calls.append(args), "unit", "2026-08",
                         {"area_land": 70, "area_tarp": -1,
                          "harvest_land": 600, "harvest_tarp": 400},
                         postgres=True)
        self.assertEqual(calls, [])


@unittest.skipUnless(os.getenv("OCOP_TEST_PG_DSN"),
                     "Set OCOP_TEST_PG_DSN to enable disposable PostgreSQL tests")
class PostgreSQLSchemaTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg import sql

        self.psycopg = psycopg
        self.admin_dsn = os.environ["OCOP_TEST_PG_DSN"]
        self.database = "ocop_test_" + uuid4().hex
        with psycopg.connect(self.admin_dsn, autocommit=True) as admin:
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(self.database)))
        self.addCleanup(self.drop_database)

    def drop_database(self):
        from psycopg import sql

        with self.psycopg.connect(self.admin_dsn, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(
                sql.Identifier(self.database)))

    def connection(self):
        return self.psycopg.connect(
            self.admin_dsn, dbname=self.database, autocommit=True,
            row_factory=backend_db.hybrid_row,
            options="-c search_path=app,qd5277,staging,public")

    def test_all_postgresql_migrations_build_application_schema(self):
        migration_names = (
            "002_qd5277_schema.sql", "004_app_schema.sql",
            "005_monthly_salt_sync.sql", "006_official_admin_units.sql",
            "007_ocop_init_only.sql", "008_ocop_dynamic_criteria.sql",
            "009_staff_role.sql", "010_weekly_salt_imports.sql",
            "011_weekly_foundation.sql", "012_admin_units.sql",
            "013_ocop_excel_import.sql",
        )
        with self.connection() as connection:
            for name in migration_names:
                connection.execute((ROOT / "database" / "sql" / name).read_text(encoding="utf-8"))
            schemas = {row[0] for row in connection.execute(
                "SELECT schema_name FROM information_schema.schemata "
                "WHERE schema_name IN ('app','qd5277','staging')")}
            self.assertEqual(schemas, {"app", "qd5277", "staging"})
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM app.schema_migrations").fetchone()[0], 10)
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM qd5277.DN_SanLuongMuoi").fetchone()[0], 0)
            admin_id = connection.execute(
                "INSERT INTO app.users(username,role,active,created_at) "
                "VALUES('catalog_admin','admin',TRUE,CURRENT_TIMESTAMP) RETURNING id"
            ).fetchone()[0]
            compat = backend_db.CompatConnection(connection)
            compat.execute("BEGIN")
            admin_units.save_unit(
                compat, {"user_id": admin_id, "role": "admin"},
                {"code": "99999", "name": "Xã kiểm thử", "level": "xa", "active": True},
            )
            self.assertEqual(admin_units.get_unit(compat, "99999")["name"], "Xã kiểm thử")
