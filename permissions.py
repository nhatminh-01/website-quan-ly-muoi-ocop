"""Shared role policy; account administration is separate from business work."""
ROLE_ADMIN = "admin"
ROLE_STAFF = "staff"
ROLE_UNIT = "unit"
ROLE_LABELS = {
    ROLE_ADMIN: "Quản trị Chi cục",
    ROLE_STAFF: "Chuyên viên Chi cục",
    ROLE_UNIT: "Đơn vị xã/phường",
}


def is_admin(session):
    return bool(session and session.get("role") == ROLE_ADMIN)


def is_chi_cuc_user(session):
    return bool(session and session.get("role") in (ROLE_ADMIN, ROLE_STAFF))


def can_manage_users(session):
    return is_admin(session)


def can_review_records(session):
    return is_chi_cuc_user(session)
