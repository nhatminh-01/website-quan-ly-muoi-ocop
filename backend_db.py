"""PostgreSQL connection boundary for the website backend.

Database DDL, ETL, and validation live in the repository's ``database``
directory. This module contains the application-side connection boundary.
"""

from __future__ import annotations

import os
import re
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Mapping, Sequence

import sqlite3
try:
    import psycopg
    from psycopg.pq import TransactionStatus
except ImportError:
    psycopg = None
    TransactionStatus = None
try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None
INTEGRITY_ERRORS = (sqlite3.IntegrityError,) + ((psycopg.IntegrityError,) if psycopg else ())


REPOSITORY_ENV_FILE = Path(__file__).resolve().parent / "database" / ".env"
LEGACY_ENV_FILE = Path(__file__).resolve().parent.parent / "DB" / ".env"


def default_env_file() -> Path:
    """Prefer portable repository config, with the original local path as fallback."""
    return REPOSITORY_ENV_FILE if REPOSITORY_ENV_FILE.is_file() else LEGACY_ENV_FILE


@dataclass(frozen=True)
class DatabaseSettings:
    host: str
    port: int
    dbname: str
    user: str
    password: str | None


def load_settings(env_file: str | os.PathLike[str] | None = None) -> DatabaseSettings:
    path = Path(env_file or os.getenv("PTNT_DB_ENV_FILE", default_env_file()))
    if not path.is_file():
        raise RuntimeError(f"Không tìm thấy cấu hình PostgreSQL: {path}")
    if load_dotenv is None:
        raise RuntimeError("PostgreSQL cần python-dotenv. Cài database/requirements.txt.")
    load_dotenv(path, override=False)
    return DatabaseSettings(
        host=os.getenv("PGHOST", "localhost"),
        port=int(os.getenv("PGPORT", "5432")),
        dbname=os.getenv("PGDATABASE", "ptnt_qd5277_dev"),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD") or None,
    )


class HybridRow(dict):
    """Mapping row compatible with the two sqlite3.Row access styles in the app."""

    def __init__(self, columns: Sequence[str], values: Sequence[object]):
        super().__init__(zip(columns, values))
        self._columns = tuple(columns)
        self._casefolded = {column.casefold(): column for column in columns}

    def __getitem__(self, key):
        if isinstance(key, int):
            return super().__getitem__(self._columns[key])
        if isinstance(key, str) and key not in self:
            key = self._casefolded.get(key.casefold(), key)
        return super().__getitem__(key)


def hybrid_row(cursor):
    columns = tuple(column.name for column in (cursor.description or ()))

    def make_row(values):
        return HybridRow(columns, values)

    return make_row


def connect(*, autocommit: bool = False) -> psycopg.Connection:
    if psycopg is None:
        raise RuntimeError("PostgreSQL cần psycopg. Cài database/requirements.txt; SQLite TEST không cần thư viện này.")
    settings = load_settings()
    return psycopg.connect(
        host=settings.host,
        port=settings.port,
        dbname=settings.dbname,
        user=settings.user,
        password=settings.password,
        autocommit=autocommit,
        row_factory=hybrid_row,
        options="-c search_path=app,qd5277,staging,public",
        application_name="ptnt_salt_ocop_web",
    )


_IDENTITY_TABLES = {
    "users",
    "records",
    "audit_logs",
    "ocop_entities",
    "ocop_products",
    "ocop_applications",
    "ocop_reviews",
    "ocop_criteria_sets",
    "ocop_criteria",
    "ocop_criteria_options",
    "salt_import_batches",
    "salt_weekly_records",
}


def _translate_placeholders(sql: str) -> str:
    """Translate SQLite placeholders while leaving quoted SQL text untouched."""
    result: list[str] = []
    i = 0
    quote: str | None = None
    while i < len(sql):
        char = sql[i]
        if quote:
            result.append("%%" if char == "%" else char)
            if char == quote:
                if i + 1 < len(sql) and sql[i + 1] == quote:
                    result.append(sql[i + 1])
                    i += 1
                else:
                    quote = None
            i += 1
            continue
        if char in ("'", '"'):
            quote = char
            result.append(char)
        elif char == "?":
            result.append("%s")
        elif char == ":" and i + 1 < len(sql) and (sql[i + 1].isalpha() or sql[i + 1] == "_"):
            match = re.match(r":([A-Za-z_][A-Za-z0-9_]*)", sql[i:])
            if match:
                result.append("%(" + match.group(1) + ")s")
                i += len(match.group(0)) - 1
            else:
                result.append(char)
        else:
            result.append(char)
        i += 1
    return "".join(result)


def translate_sql(sql: str) -> tuple[str, str | None]:
    """Return PostgreSQL SQL and the inserted identity table, when applicable."""
    translated = _translate_placeholders(sql)
    translated = re.sub(r"\bBEGIN\s+IMMEDIATE\b", "BEGIN", translated, flags=re.I)
    translated = re.sub(r"\bCOLLATE\s+BINARY\b", "", translated, flags=re.I)
    translated = re.sub(
        r"\b(active|TinhTrang)\s*=\s*1\b",
        lambda match: f"{match.group(1)}=TRUE",
        translated,
        flags=re.I,
    )
    translated = re.sub(
        r"\b(active|TinhTrang)\s*=\s*0\b",
        lambda match: f"{match.group(1)}=FALSE",
        translated,
        flags=re.I,
    )
    translated = re.sub(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", "INSERT INTO", translated, flags=re.I)
    translated = re.sub(r"\bIS\s+NOT\s+%s\b", "IS DISTINCT FROM %s", translated, flags=re.I)

    insert = re.match(r"\s*INSERT\s+INTO\s+(?:[A-Za-z_][\w]*\.)?([A-Za-z_][\w]*)", translated, re.I)
    table = insert.group(1).casefold() if insert else None
    identity_table = table if table in _IDENTITY_TABLES else None
    if "INSERT OR IGNORE" in sql.upper() and "ON CONFLICT" not in translated.upper():
        translated = translated.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    if identity_table and "RETURNING" not in translated.upper():
        translated = translated.rstrip().rstrip(";") + " RETURNING id"
    return translated, identity_table


class CompatCursor:
    def __init__(self, cursor, *, lastrowid=None, buffered_rows=None):
        self._cursor = cursor
        self.lastrowid = lastrowid
        self._buffered_rows = list(buffered_rows or [])

    @property
    def description(self):
        return self._cursor.description

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def fetchone(self):
        if self._buffered_rows:
            return self._buffered_rows.pop(0)
        return self._cursor.fetchone()

    def fetchall(self):
        rows = self._buffered_rows
        self._buffered_rows = []
        return rows + self._cursor.fetchall()

    def __iter__(self):
        return iter(self.fetchall())


class CompatConnection:
    """Small sqlite3-like boundary used while preserving existing HTTP handlers."""

    def __init__(self, connection: psycopg.Connection):
        self._connection = connection

    @property
    def in_transaction(self) -> bool:
        return self._connection.info.transaction_status != TransactionStatus.IDLE

    def execute(self, sql: str, params: Sequence | Mapping | None = None) -> CompatCursor:
        translated, identity_table = translate_sql(sql)
        # Match sqlite3: SELECT alone does not start a transaction; the first
        # write does. This lets OCOP own its transaction even after page checks.
        if (self._connection.autocommit and not self.in_transaction
                and re.match(r"\s*(INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|TRUNCATE)\b", translated, re.I)):
            self._connection.execute("BEGIN")
        cursor = self._connection.execute(translated, params or ())
        lastrowid = None
        buffered_rows = []
        if identity_table:
            returned = cursor.fetchone()
            if returned is not None:
                lastrowid = returned[0]
        return CompatCursor(cursor, lastrowid=lastrowid, buffered_rows=buffered_rows)

    def executemany(self, sql: str, params_seq) -> CompatCursor:
        translated, _ = translate_sql(sql)
        if self._connection.autocommit and not self.in_transaction:
            self._connection.execute("BEGIN")
        cursor = self._connection.cursor()
        cursor.executemany(translated, params_seq)
        return CompatCursor(cursor)

    def commit(self):
        return self._connection.commit()

    def rollback(self):
        return self._connection.rollback()

    def close(self):
        return self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return self._connection.__exit__(exc_type, exc_value, traceback)


def compat_connect() -> CompatConnection:
    return CompatConnection(connect(autocommit=True))


@contextmanager
def transaction() -> Iterator[psycopg.Connection]:
    connection = connect()
    try:
        with connection.transaction():
            yield connection
    finally:
        connection.close()


def healthcheck() -> dict[str, object]:
    with connect(autocommit=True) as connection:
        row = connection.execute(
            """
            SELECT current_database() AS database,
                   current_user AS db_user,
                   current_schema() AS default_schema,
                   current_setting('server_version') AS server_version
            """
        ).fetchone()
        schemas = connection.execute(
            """
            SELECT table_schema, COUNT(*)::INTEGER AS tables
            FROM information_schema.tables
            WHERE table_schema IN ('app', 'qd5277', 'staging')
            GROUP BY table_schema
            ORDER BY table_schema
            """
        ).fetchall()
    return {**row, "schemas": schemas}
