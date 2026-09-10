"""PostgreSQL repositories for application-owned data.

The HTTP layer keeps its existing pages and routes.  Password credentials are
kept outside the user profile so a future VNeID identity can coexist cleanly.
"""

from __future__ import annotations


def get_user(con, user_id):
    return con.execute(
        """SELECT u.*, c.password_hash
           FROM users u
           LEFT JOIN user_credentials c ON c.user_id=u.id
           WHERE u.id=?""",
        (user_id,),
    ).fetchone()


def find_user_by_username(con, username):
    return con.execute(
        """SELECT u.*, c.password_hash
           FROM users u
           JOIN user_credentials c ON c.user_id=u.id
           WHERE u.username=?""",
        (username,),
    ).fetchone()


def list_users(con):
    return con.execute(
        """SELECT u.*, c.password_hash
           FROM users u
           LEFT JOIN user_credentials c ON c.user_id=u.id
           ORDER BY u.role, u.unit_name, u.username"""
    ).fetchall()


def create_user(con, username, password_hash, role, unit_name, created_at, *, active=True):
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
    con.execute(
        "UPDATE users SET username=?,role=?,unit_name=?,active=? WHERE id=?",
        (username, role, unit_name, bool(active), user_id),
    )
    if password_hash is not None:
        set_local_password(con, user_id, password_hash)


def set_local_password(con, user_id, password_hash):
    con.execute(
        """INSERT INTO user_credentials(user_id,password_hash,password_updated_at)
           VALUES(?,?,CURRENT_TIMESTAMP)
           ON CONFLICT(user_id) DO UPDATE SET
             password_hash=excluded.password_hash,
             password_updated_at=CURRENT_TIMESTAMP""",
        (user_id, password_hash),
    )


def delete_user(con, user_id):
    con.execute("DELETE FROM user_identities WHERE user_id=?", (user_id,))
    con.execute("DELETE FROM user_credentials WHERE user_id=?", (user_id,))
    con.execute("DELETE FROM users WHERE id=?", (user_id,))


def postgres_application_ready(con):
    required = {
        "users", "user_credentials", "user_identities", "records", "audit_logs",
        "user_admin_units", "ocop_entities", "ocop_products", "ocop_applications",
        "ocop_reviews", "ocop_criteria_sets", "ocop_criteria", "ocop_criteria_options",
        "salt_import_batches", "salt_weekly_records",
    }
    rows = con.execute(
        """SELECT table_name FROM information_schema.tables
           WHERE table_schema='app'"""
    ).fetchall()
    return required <= {row[0] for row in rows}


def set_user_active(con, user_id, active):
    con.execute("UPDATE users SET active=? WHERE id=?", (bool(active), user_id))
