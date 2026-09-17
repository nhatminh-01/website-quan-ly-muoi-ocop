"""Dashboard data services shared by the HTTP pages and future dashboards.

This module owns dashboard aggregation and scope handling.  It deliberately
reuses :func:`weekly_import.effective_weekly_dashboard` for the salt module so
there is still one definition of an effective weekly period.
"""

from __future__ import annotations

from collections.abc import Mapping

import ocop_services
from weekly_import import effective_weekly_dashboard


_SALT_METRICS = {
    "area": {"total": "dien_tich", "land": "area_land", "tarp": "area_tarp"},
    "harvest": {"total": "san_luong", "land": "harvest_land", "tarp": "harvest_tarp"},
    "consumption": {"total": "sold_total", "land": "sold_land", "tarp": "sold_tarp"},
    "remaining": {"total": "remaining_total", "land": "remaining_land", "tarp": "remaining_tarp"},
    "households": {"total": "households"},
    "workers": {"total": "workers"},
}


def _value(filters: Mapping | None, key: str, default=""):
    value = (filters or {}).get(key, default)
    if isinstance(value, (list, tuple)):
        return value[0] if value else default
    return default if value is None else value


def _sum_column(rows, column):
    """Sum present values without turning an all-NULL metric into zero."""
    values = [row.get(column) for row in rows if row.get(column) is not None]
    if not values:
        return None
    return sum(float(value) for value in values)


def _aggregate_salt_rows(rows):
    return {
        metric: {
            component: _sum_column(rows, column)
            for component, column in columns.items()
        }
        for metric, columns in _SALT_METRICS.items()
    }


def _change(current, previous):
    if current is None or previous is None:
        return {"previous": previous, "delta": None, "percent_change": None}
    delta = current - previous
    return {
        "previous": previous,
        "delta": delta,
        "percent_change": (delta / previous * 100) if previous != 0 else None,
    }


def _changes(current, previous):
    return {
        metric: {
            component: _change(
                current.get(metric, {}).get(component),
                previous.get(metric, {}).get(component),
            )
            for component in columns
        }
        for metric, columns in _SALT_METRICS.items()
    }


def _salt_unit_scope(con, session, filters):
    """Return the authorized salt unit code and the selected display name."""
    scope = ocop_services.get_scope(con, session)
    selected = str(_value(filters, "unit_code", _value(filters, "unit", ""))).strip()
    if scope is not None:
        if selected and selected != scope:
            # Reuse the existing OCOP unit validation, including its permission
            # error, instead of introducing a second permission policy.
            ocop_services._check_unit(con, session, selected)
        unit_code = scope
    else:
        unit_code = selected or None
        if unit_code:
            ocop_services._check_unit(con, session, unit_code)

    if not unit_code:
        unit_name = "Tất cả đơn vị"
    elif scope is not None:
        unit_name = str(session.get("unit_name") or unit_code)
    else:
        unit = con.execute(
            "SELECT TenDonVi FROM DM_DonViHanhChinh WHERE Ma_DonViHanhChinh=?",
            (unit_code,),
        ).fetchone()
        unit_name = unit["TenDonVi"] if unit else unit_code
    return unit_code, unit_name


def _unit_breakdown(rows):
    """Aggregate the selected effective period by administrative unit."""
    grouped = {}
    for row in rows:
        code = row.get("ma_don_vi_hanh_chinh") or ""
        key = (code, row.get("unit_name") or code)
        grouped.setdefault(key, []).append(row)
    result = []
    for (code, name), unit_rows in sorted(grouped.items(), key=lambda item: item[0][1]):
        item = {"unit_code": code, "unit_name": name, "reports": len(unit_rows)}
        item.update(_aggregate_salt_rows(unit_rows))
        result.append(item)
    return result


def get_salt_dashboard(con, session, filters=None):
    """Return the effective salt dashboard model for the authorized scope.

    ``effective_weekly_dashboard`` remains responsible for selecting the
    current and previous effective weeks.  This service only aggregates its
    rows and calculates comparable deltas for the renderer/API consumer.
    """
    filters = filters or {}
    unit_code, unit_name = _salt_unit_scope(con, session, filters)
    data = effective_weekly_dashboard(
        con,
        week=str(_value(filters, "week", "")).strip(),
        batch=str(_value(filters, "batch", "")).strip(),
        unit_code=unit_code,
    )
    if data is None:
        return None

    current_rows = data["rows"]
    previous_rows = data["previous_rows"]
    current_metrics = _aggregate_salt_rows(current_rows)
    previous_metrics = _aggregate_salt_rows(previous_rows)
    return {
        # Preserve the period/row model already consumed by the legacy page.
        "periods": data["periods"],
        "selected": data["selected"],
        "previous": data["previous"],
        "rows": current_rows,
        "previous_rows": previous_rows,
        "warning_rows": data["warning_rows"],
        "scope": {"unit_code": unit_code, "unit_name": unit_name},
        "current_period": data["selected"],
        "previous_period": data["previous"],
        "current_metrics": current_metrics,
        "previous_metrics": previous_metrics,
        "changes": _changes(current_metrics, previous_metrics),
        "unit_breakdown": _unit_breakdown(current_rows),
    }


def get_salt_import_counts(con, session):
    """Return imported batch/row counts within the user's existing scope."""
    scope = ocop_services.get_scope(con, session)
    if scope is None:
        row = con.execute(
            """SELECT
                 (SELECT COUNT(*) FROM salt_import_batches) AS import_batches,
                 (SELECT COUNT(*) FROM salt_weekly_records) AS import_rows"""
        ).fetchone()
    else:
        row = con.execute(
            """SELECT
                 (SELECT COUNT(*) FROM salt_import_batches b
                  WHERE EXISTS (SELECT 1 FROM salt_weekly_records r
                                WHERE r.batch_id=b.id
                                  AND r.ma_don_vi_hanh_chinh=?)) AS import_batches,
                 (SELECT COUNT(*) FROM salt_weekly_records
                  WHERE ma_don_vi_hanh_chinh=?) AS import_rows""",
            (scope, scope),
        ).fetchone()
    return {
        "import_batches": int(row["import_batches"] or 0),
        "import_rows": int(row["import_rows"] or 0),
    }


def get_ocop_dashboard(con, session, filters=None):
    """Return the OCOP dashboard summary, reusing the Plan 02 service."""
    return ocop_services.get_ocop_expiry_summary(con, session, filters)


def get_ocop_catalog_counts(con, session, filters=None):
    """Return legacy home-card counts while applying the current scope."""
    scope = ocop_services.get_scope(con, session)
    selected = str(_value(filters, "unit_code", _value(filters, "unit", ""))).strip()
    if scope is not None:
        if selected and selected != scope:
            ocop_services._check_unit(con, session, selected)
    elif selected:
        ocop_services._check_unit(con, session, selected)
        scope = selected
    unit_predicate = " AND c.Ma_DonViHanhChinh=?" if scope else ""
    product_predicate = " AND p.ma_don_vi_hanh_chinh=?" if scope else ""
    args = [scope, scope] if scope else []
    sql = (
        """SELECT
             (SELECT COUNT(*) FROM ocop_entities e
              JOIN DM_CoSo c ON c.Ma_CoSo=e.ma_co_so
              WHERE e.archived_at IS NULL"""
        + unit_predicate
        + """ ) AS entities,
             (SELECT COUNT(*) FROM ocop_products p
              WHERE p.status='active'"""
        + product_predicate
        + """ ) AS products"""
    )
    row = con.execute(sql, args).fetchone()
    return {
        "entities": int(row["entities"] or 0),
        "products": int(row["products"] or 0),
    }


def get_home_dashboard(con, session):
    """Return the data currently needed by the compact home dashboard."""
    ocop_summary = get_ocop_dashboard(con, session)
    catalog_counts = get_ocop_catalog_counts(con, session)
    return {
        "salt": get_salt_import_counts(con, session),
        "ocop": {
            **catalog_counts,
            "summary": ocop_summary,
        },
    }


def get_dashboard_data(con, session, *, salt_filters=None, ocop_filters=None):
    """Return the combined model planned for the future common dashboard."""
    salt = get_salt_dashboard(con, session, salt_filters)
    ocop_summary = get_ocop_dashboard(con, session, ocop_filters)
    catalog = get_ocop_catalog_counts(con, session, ocop_filters)
    return {
        "salt": salt,
        "ocop": {
            **ocop_summary,
            "managed_products": catalog["products"],
            "managed_entities": catalog["entities"],
        },
    }


def get_dashboard_unit_options(con, session):
    """Return the existing authorized commune/ward catalog for dashboard filters."""
    return ocop_services.unit_options(con, session)
