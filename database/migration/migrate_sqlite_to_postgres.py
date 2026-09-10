"""Copy SQLite to PostgreSQL during maintenance, after SQL 002,004..009.

Read-only source; atomic target transaction; preserve IDs and refuse collisions.
Back up the target first. No official OCOP results are created or copied here.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from backend_db import connect, CompatConnection
from salt_normalization import sync_methods

DEFAULT_SOURCE = ROOT / 'salt_management.db'
# Dependency order, primary key, and identity fields used to reject ID collisions.
TABLES = (
    ('DM_DonViHanhChinh', 'qd5277', 'Ma_DonViHanhChinh', ()),
    ('DM_KhoangThoiGian', 'qd5277', 'Ma_ThoiGian', ()),
    ('users', 'app', 'id', ('username',)),
    ('DM_SanPham', 'qd5277', 'Ma_SanPham', ()),
    ('DM_CoSo', 'qd5277', 'Ma_CoSo', ()),
    ('user_admin_units', 'app', 'user_id', ()),
    ('ocop_criteria_sets', 'app', 'id', ('code',)),
    ('ocop_criteria', 'app', 'id', ('criteria_set_id', 'code')),
    ('ocop_criteria_options', 'app', 'id', ('criterion_id',)),
    ('ocop_entities', 'app', 'id', ('ma_co_so',)),
    ('ocop_products', 'app', 'id', ('ma_san_pham',)),
    ('ocop_applications', 'app', 'id', ('product_id', 'created_by')),
    ('ocop_reviews', 'app', 'id', ('application_id', 'reviewer_id')),
    ('records', 'app', 'id', ('unit_name', 'report_date')),
    ('audit_logs', 'app', 'id', ('record_id', 'user_id', 'module', 'object_id')),
)


def source_snapshot(path):
    con = sqlite3.connect(Path(path).resolve(strict=True).as_uri() + '?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    try:
        con.execute('BEGIN')
        if con.execute('PRAGMA foreign_key_check').fetchall():
            raise RuntimeError('SQLite source has foreign-key errors; no target changes made.')
        names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return {name: [dict(r) for r in con.execute(f'SELECT * FROM "{name}"')]
                for name, _, _, _ in TABLES if name in names}
    finally:
        con.close()


def parent_first(rows, key, parent):
    remaining = {r[key]: r for r in rows}
    result = []
    while remaining:
        ready = [r for r in remaining.values() if r.get(parent) not in remaining]
        if not ready:
            raise RuntimeError(f'Cycle in source {parent} tree.')
        for row in ready:
            result.append(row)
            del remaining[row[key]]
    return result


def reset_identity(target, table):
    """Use transactional ALTER SEQUENCE, without rewinding an existing counter."""
    from psycopg import sql
    sequence = target.execute('SELECT pg_get_serial_sequence(%s,%s)', ('app.' + table, 'id')).fetchone()[0]
    if not sequence:
        return
    last = target.execute(sql.SQL('SELECT last_value FROM {}').format(sql.Identifier(*sequence.split('.')))).fetchone()[0]
    maximum = target.execute(sql.SQL('SELECT COALESCE(MAX(id),0) FROM app.{}').format(sql.Identifier(table))).fetchone()[0]
    target.execute(sql.SQL('ALTER SEQUENCE {} RESTART WITH {}').format(
        sql.Identifier(*sequence.split('.')), sql.Literal(max(last, maximum) + 1)))


def copy_table(target, name, schema, key, identity, rows):
    from psycopg import sql
    columns = {r[0]: r[1] for r in target.execute(
        'SELECT column_name,data_type FROM information_schema.columns WHERE table_schema=%s AND table_name=%s',
        (schema, name.lower()))}
    if not columns:
        raise RuntimeError(f'Missing target {schema}.{name}; apply schema migrations first.')
    table = sql.Identifier(schema, name.lower())
    for raw in rows:
        row = {k.lower(): v for k, v in raw.items()}
        if name == 'users':
            password = row.pop('password_hash')
            from server import canonical_admin_unit
            canonical = canonical_admin_unit(row.get('unit_name'))
            if canonical and row['role'] == 'unit':
                row['unit_name'] = canonical[0]
        if name == 'records':
            from server import canonical_admin_unit
            canonical = canonical_admin_unit(row['unit_name'])
            if not canonical:
                raise RuntimeError('Unknown administrative unit in report: ' + row['unit_name'])
            row.update(unit_name=canonical[0], ma_don_vi_hanh_chinh=canonical[1])
            row.setdefault('reporting_mode', 'cumulative')
        unknown = set(row) - set(columns)
        if unknown:
            raise RuntimeError(f'Unmapped source columns in {name}: {sorted(unknown)}')
        for col, value in list(row.items()):
            if columns[col] == 'boolean' and value is not None:
                if value not in (0, 1, False, True):
                    raise RuntimeError(f'Invalid boolean {name}.{col}')
                row[col] = bool(value)
        existing = target.execute(sql.SQL('SELECT * FROM {} WHERE {}=%s').format(table, sql.Identifier(key.lower())), (row[key.lower()],)).fetchone()
        if existing:
            for col in identity:
                before, after = existing[col], row.get(col)
                if str(before if before is not None else '') != str(after if after is not None else ''):
                    raise RuntimeError(f'ID collision in {name}: {row[key.lower()]}; target identity differs.')
        names = list(row)
        updates = [c for c in names if c != key.lower()]
        target.execute(sql.SQL('INSERT INTO {} ({}) VALUES ({}) ON CONFLICT ({}) DO UPDATE SET {}').format(
            table, sql.SQL(',').join(map(sql.Identifier, names)),
            sql.SQL(',').join(sql.Placeholder() for _ in names), sql.Identifier(key.lower()),
            sql.SQL(',').join(sql.SQL('{}=excluded.{}').format(sql.Identifier(c),sql.Identifier(c)) for c in updates)), tuple(row.values()))
        if name == 'users':
            target.execute('INSERT INTO app.user_credentials(user_id,password_hash) VALUES(%s,%s) ON CONFLICT(user_id) DO UPDATE SET password_hash=excluded.password_hash', (row['id'], password))


def repair_salt(target):
    """Only repair periods backed by an approved cumulative source report."""
    con = CompatConnection(target)
    rows = target.execute("""SELECT DISTINCT ON (ma_don_vi_hanh_chinh, date_trunc('month',report_date)) *
        FROM app.records WHERE status='approved' AND reporting_mode='cumulative'
          AND ma_don_vi_hanh_chinh IS NOT NULL
        ORDER BY ma_don_vi_hanh_chinh,date_trunc('month',report_date),report_date DESC,id DESC""").fetchall()
    for row in rows:
        day = row['report_date']
        code = day.strftime('%Y-%m')
        con.execute('INSERT INTO DM_KhoangThoiGian(Ma_ThoiGian,Nam,Thang) VALUES(?,?,?) ON CONFLICT(Ma_ThoiGian) DO NOTHING', (code,day.year,day.month))
        sync_methods(con.execute, row['ma_don_vi_hanh_chinh'], code, row, postgres=True)
    return len(rows)


def migrate(source_path, *, target=None, dry_run=False):
    snapshot = source_snapshot(source_path)
    own = target is None
    target = target or connect()
    try:
        with target.transaction(force_rollback=dry_run):
            target.execute('SELECT pg_advisory_xact_lock(5277009)')
            for name, schema, _, _ in TABLES:
                if name in snapshot:
                    target.execute(f'LOCK TABLE {schema}.{name} IN SHARE ROW EXCLUSIVE MODE')
            for name, schema, key, identity in TABLES:
                if name not in snapshot:
                    continue
                rows = snapshot[name]
                if name == 'DM_DonViHanhChinh':
                    rows = parent_first(rows,key,'Ma_DonViCapTren')
                if name == 'ocop_criteria':
                    rows = parent_first(rows,key,'parent_id')
                copy_table(target,name,schema,key,identity,rows)
            if 'user_admin_units' not in snapshot:
                from server import canonical_admin_unit
                for row in snapshot.get('users', []):
                    unit = canonical_admin_unit(row.get('unit_name'))
                    if row['role'] == 'unit' and unit:
                        target.execute('INSERT INTO app.user_admin_units VALUES(%s,%s) ON CONFLICT(user_id) DO NOTHING', (row['id'],unit[1]))
            repair_salt(target)
            for name,schema,key,_ in TABLES:
                if name in snapshot and schema == 'app' and key == 'id':
                    reset_identity(target,name)
            target.execute("INSERT INTO app.schema_migrations(version) VALUES('app_008_sqlite_ocop_data') ON CONFLICT(version) DO NOTHING")
        return {name:len(rows) for name,rows in snapshot.items()}
    finally:
        if own:
            target.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    parser.add_argument('--dry-run', action='store_true', help='Execute validation then roll back the transaction.')
    parser.add_argument('--repair-salt-only', action='store_true', help='Repair from PostgreSQL records; do not read SQLite.')
    args = parser.parse_args()
    if args.repair_salt_only:
        with connect() as target:
            with target.transaction(force_rollback=args.dry_run):
                target.execute('LOCK TABLE app.records, qd5277.DN_SanLuongMuoi IN SHARE ROW EXCLUSIVE MODE')
                print('Periods:', repair_salt(target))
    else:
        print(migrate(args.source, dry_run=args.dry_run))
    print('Rolled back (dry run).' if args.dry_run else 'Committed. PTNT_OCOP was not modified.')


if __name__ == '__main__':
    main()
