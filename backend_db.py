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

import psycopg
from psycopg.pq import TransactionStatus
from dotenv import load_dotenv

INTEGRITY_ERRORS = (psycopg.IntegrityError,)


REPOSITORY_ENV_FILE = Path(__file__).resolve().parent / "database" / ".env"


def default_env_file() -> Path:
    """Use the untracked PostgreSQL configuration stored inside this checkout."""
    return REPOSITORY_ENV_FILE


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
    """Case-insensitive PostgreSQL row supporting name and numeric lookup."""

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
    "ocop_import_batches",
    "ocop_import_errors",
    "ocop_recognitions",
}

_BOOLEAN_LITERAL_RE = re.compile(
    r"\b(active|TinhTrang)\b\s*=\s*([01])\b",
    re.IGNORECASE,
)


def _translate_placeholders(sql: str) -> str:
    """Translate the handlers' compact placeholders to psycopg syntax."""
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


def _translate_boolean_literals(sql: str) -> str:
    """Adapt legacy SQLite boolean predicates to PostgreSQL booleans.

    The application schema defines ``active`` and ``TinhTrang`` as BOOLEAN. Some
    mature handlers still use SQLite-style ``=1``/``=0`` predicates. Rewrite only
    SQL outside single-quoted string literals so literal text is never altered.
    """
    def replace(match: re.Match) -> str:
        return f"{match.group(1)}={'TRUE' if match.group(2) == '1' else 'FALSE'}"

    result: list[str] = []
    start = 0
    i = 0
    in_string = False
    while i < len(sql):
        if sql[i] != "'":
            i += 1
            continue
        if in_string and i + 1 < len(sql) and sql[i + 1] == "'":
            i += 2
            continue
        if in_string:
            result.append(sql[start:i + 1])
            start = i + 1
            in_string = False
        else:
            result.append(_BOOLEAN_LITERAL_RE.sub(replace, sql[start:i]))
            start = i
            in_string = True
        i += 1
    tail = sql[start:]
    result.append(tail if in_string else _BOOLEAN_LITERAL_RE.sub(replace, tail))
    return "".join(result)


def translate_sql(sql: str) -> tuple[str, str | None]:
    """Return PostgreSQL SQL and the inserted identity table, when applicable."""
    translated = _translate_boolean_literals(_translate_placeholders(sql))

    insert = re.match(r"\s*INSERT\s+INTO\s+(?:[A-Za-z_][\w]*\.)?([A-Za-z_][\w]*)", translated, re.I)
    table = insert.group(1).casefold() if insert else None
    identity_table = table if table in _IDENTITY_TABLES else None
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
    """Small PostgreSQL adapter used by the existing HTTP handlers."""

    def __init__(self, connection: psycopg.Connection):
        self._connection = connection

    @property
    def in_transaction(self) -> bool:
        return self._connection.info.transaction_status != TransactionStatus.IDLE

    def execute(self, sql: str, params: Sequence | Mapping | None = None) -> CompatCursor:
        translated, identity_table = translate_sql(sql)
        # Keep reads in autocommit; start an explicit transaction on first write.
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
