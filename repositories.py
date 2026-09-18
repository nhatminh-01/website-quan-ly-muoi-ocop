"""PostgreSQL repositories for application-owned data.

The HTTP layer keeps its existing pages and routes.  Password credentials are
kept outside the user profile so a future VNeID identity can coexist cleanly.
"""

from __future__ import annotations

from permissions import is_legacy_account


class ArchivedAccountError(ValueError):
    """An archived identity cannot be repurposed or deleted."""


ARCHIVED_ACCOUNT_MESSAGE = "Tài khoản xã/phường (cũ) chỉ lưu lịch sử; không thể chỉnh sửa, kích hoạt hoặc xóa."


def _require_mutable_user(con, user_id):
    # Lock the identity until the caller commits its account transaction.
    user = con.execute("SELECT role FROM users WHERE id=? FOR UPDATE", (user_id,)).fetchone()
    if is_legacy_account(user):
        raise ArchivedAccountError(ARCHIVED_ACCOUNT_MESSAGE)


def get_user(con, user_id):
    return con.execute(
        """SELECT u.*, c.password_hash
           FROM users u
           LEFT JOIN user_credentials c ON c.user_id=u.id
           WHERE u.id=?""",
        (user_id,),
    ).fetchone()


def find_user_by_username(con, username):
    """Authenticate only active deployment roles; legacy unit rows stay queryable elsewhere."""
    return con.execute(
        """SELECT u.*, c.password_hash
           FROM users u
           JOIN user_credentials c ON c.user_id=u.id
           WHERE u.username=? AND u.role IN ('admin','staff')""",
        (username,),
    ).fetchone()


def list_users(con, *, include_legacy=False):
    return con.execute(
        """SELECT u.*, c.password_hash
           FROM users u
           LEFT JOIN user_credentials c ON c.user_id=u.id
           WHERE u.role IN ('admin','staff')
              OR (? AND u.role IN ('unit','legacy'))
           ORDER BY u.role, u.unit_name, u.username""",
        (bool(include_legacy),),
    ).fetchall()


def create_user(con, username, password_hash, role, unit_name, created_at, *, active=True):
    # Historical imports/fixtures can retain legacy identities, never access.
    active = bool(active) and not is_legacy_account({"role": role})
    cursor = con.execute(
        """INSERT INTO users(username,role,unit_name,active,created_at)
           VALUES(?,?,?,?,?)""",
        (username, role, unit_name, active, created_at),
    )
    user_id = cursor.lastrowid
    con.execute(
        "INSERT INTO user_credentials(user_id,password_hash) VALUES(?,?)",
        (user_id, password_hash),
    )
    return user_id


def update_user(con, user_id, username, role, unit_name, active, password_hash=None):
    _require_mutable_user(con, user_id)
    if role not in ("admin", "staff"):
        raise ArchivedAccountError("Chỉ được sử dụng vai trò Quản trị Chi cục hoặc Chuyên viên.")
    con.execute(
        "UPDATE users SET username=?,role=?,unit_name=?,active=? WHERE id=?",
        (username, role, unit_name, bool(active), user_id),
    )
    if password_hash is not None:
        set_local_password(con, user_id, password_hash)


def set_local_password(con, user_id, password_hash):
    _require_mutable_user(con, user_id)
    con.execute(
        """INSERT INTO user_credentials(user_id,password_hash,password_updated_at)
           VALUES(?,?,CURRENT_TIMESTAMP)
           ON CONFLICT(user_id) DO UPDATE SET
             password_hash=excluded.password_hash,
             password_updated_at=CURRENT_TIMESTAMP""",
        (user_id, password_hash),
    )


def delete_user(con, user_id):
    _require_mutable_user(con, user_id)
    con.execute("DELETE FROM user_identities WHERE user_id=?", (user_id,))
    con.execute("DELETE FROM user_credentials WHERE user_id=?", (user_id,))
    con.execute("DELETE FROM users WHERE id=?", (user_id,))


def postgres_application_ready(con):
    required = {
        "users", "user_credentials", "user_identities", "records", "audit_logs",
        "user_admin_units", "ocop_entities", "ocop_products", "ocop_applications",
        "ocop_reviews", "ocop_criteria_sets", "ocop_criteria", "ocop_criteria_options",
        "salt_import_batches", "salt_weekly_records", "admin_unit_aliases",
    }
    rows = con.execute(
        """SELECT table_name FROM information_schema.tables
           WHERE table_schema='app'"""
    ).fetchall()
    return required <= {row[0] for row in rows}


def set_user_active(con, user_id, active):
    _require_mutable_user(con, user_id)
    con.execute("UPDATE users SET active=? WHERE id=?", (bool(active), user_id))
