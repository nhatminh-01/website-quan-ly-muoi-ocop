"""Explicit SQLite role migration, with backup and atomic table replacement.

SQLite cannot ALTER a CHECK constraint. Follow its documented generalized
ALTER TABLE procedure, retaining original columns, indexes, triggers and IDs.
Run during maintenance with the web server stopped; never runs on import.
"""
import argparse
from pathlib import Path
import re
import sqlite3
from datetime import datetime


ROLE_CHECK = re.compile(r"role\s+IN\s*\(\s*'admin'\s*,\s*'unit'\s*\)", re.I)


def migrate(con):
    if con.in_transaction:
        raise RuntimeError("Role migration requires a connection without an open transaction.")
    original = con.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
    if not original:
        raise RuntimeError("Missing users table.")
    sql = original[0]
    if not ROLE_CHECK.search(sql):
        if re.search(r"role\s+IN\s*\(\s*'admin'\s*,\s*'staff'\s*,\s*'unit'\s*\)", sql, re.I):
            return False
        raise RuntimeError("Unknown role constraint; inspect schema before migrating.")
    fk = con.execute("PRAGMA foreign_keys").fetchone()[0]
    legacy_alter = con.execute("PRAGMA legacy_alter_table").fetchone()[0]
    con.execute("PRAGMA foreign_keys=OFF")
    # References in views remain users during the drop/rename window.
    con.execute("PRAGMA legacy_alter_table=ON")
    try:
        con.execute("BEGIN IMMEDIATE")
        if con.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("Existing foreign-key errors; no changes applied.")
        objects = con.execute("SELECT sql FROM sqlite_master WHERE tbl_name='users' AND type IN ('index','trigger') AND sql IS NOT NULL").fetchall()
        columns = [row[1] for row in con.execute("PRAGMA table_xinfo(users)") if row[6] == 0]
        quoted = ','.join('"' + name.replace('"', '""') + '"' for name in columns)
        sequence = con.execute("SELECT seq FROM sqlite_sequence WHERE name='users'").fetchone()
        new_sql = ROLE_CHECK.sub("role IN ('admin','staff','unit')", sql)
        new_sql, count = re.subn(r'(?i)^(CREATE TABLE\s+)(?:"users"|users)', r'\1users_role_upgrade', new_sql, count=1)
        if count != 1:
            raise RuntimeError("Cannot safely rewrite users DDL.")
        con.execute(new_sql)
        con.execute(f'INSERT INTO users_role_upgrade({quoted}) SELECT {quoted} FROM users')
        con.execute("DROP TABLE users")
        con.execute("ALTER TABLE users_role_upgrade RENAME TO users")
        for (ddl,) in objects:
            con.execute(ddl)
        if sequence:
            con.execute("UPDATE sqlite_sequence SET seq=max(seq,?) WHERE name='users'", (sequence[0],))
        if con.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("Foreign-key verification failed; migration rolled back.")
        if con.execute("PRAGMA integrity_check").fetchone()[0] != 'ok':
            raise RuntimeError("Integrity verification failed; migration rolled back.")
        con.commit()
        return True
    except Exception:
        con.rollback()
        raise
    finally:
        con.execute(f"PRAGMA legacy_alter_table={legacy_alter}")
        con.execute(f"PRAGMA foreign_keys={fk}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True, type=Path)
    args = parser.parse_args()
    path = args.db.resolve(strict=True)
    con = sqlite3.connect(path.as_uri() + '?mode=rw', uri=True)
    try:
        ddl = con.execute("SELECT sql FROM sqlite_master WHERE name='users'").fetchone()
        if ddl and ROLE_CHECK.search(ddl[0]):
            backup = path.with_name(path.name + '.before-staff-' + datetime.now().strftime('%Y%m%d%H%M%S%f') + '.bak')
            with sqlite3.connect(backup) as target:
                con.backup(target)
            print('Backup:', backup)
        print('Role migration:', 'applied' if migrate(con) else 'already applied')
    finally:
        con.close()


if __name__ == '__main__':
    main()
