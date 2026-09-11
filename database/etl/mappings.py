"""Administrative lookup for the legacy Excel snapshot, using the shared catalog."""
from admin_units import normalize as normalize_label, unit_lookup

TIME_CODE = "2026-08"


def lookup_admin_code(con, name):
    unit = unit_lookup(con)(name)
    if unit is None:
        raise ValueError(f"Chưa có xã/phường hoạt động trong danh mục: {name!r}")
    return unit[1]
