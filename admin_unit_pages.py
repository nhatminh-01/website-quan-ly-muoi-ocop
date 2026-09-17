"""Administrative catalog pages using the application's existing layout."""
from html import escape
from urllib.parse import parse_qs, quote, urlencode
import admin_units


def esc(value):
    return escape(str(value or ""), quote=True)


def select_options(rows, selected="", blank="Chọn đơn vị"):
    result = f'<option value="">{esc(blank)}</option>'
    for row in rows:
        result += f'<option value="{esc(row["code"])}" {"selected" if row["code"] == selected else ""}>{esc(row["name"])} ({esc(row["code"])})</option>'
    return result


def account_fields(con, user=None):
    user = dict(user) if user else {"role":"staff"}
    mapping = con.execute("SELECT ma_don_vi_hanh_chinh FROM user_admin_units WHERE user_id=?", (user.get("id"),)).fetchone()
    selected = mapping[0] if mapping else ""
    options = select_options(admin_units.units(con, active_only=True, communes_only=True), selected)
    current = admin_units.get_unit(con, selected) if selected else None
    if current and not current["active"]:
        options += f'<option selected disabled value="{esc(selected)}">{esc(current["name"])} — đã ngưng; chọn địa bàn hoạt động</option>'
    unit = user["role"] == "unit"
    agency = admin_units.CHI_CUC_AGENCY_NAME
    return f'''<div class="field" data-unit-field {"" if unit else "hidden"}>
      <label>Đơn vị hành chính cấp xã đang hoạt động</label><select name="unit_code" {"required" if unit else "disabled"}>{options}</select></div>
      <div class="field" data-office-field {"hidden" if unit else ""}><label>Tên cơ quan</label>
      <input name="unit_name" value="{esc(agency)}" readonly aria-readonly="true" {"disabled" if unit else "required"}></div>'''


def listing(con, session, query, csrf, flash=""):
    admin_units.require_admin(con, session)
    params = parse_qs(query)
    search = params.get("q", [""])[0].strip()
    level = params.get("level", [""])[0]
    if level not in admin_units.CURRENT_LEVELS:
        level = ""
    try:
        page_size = int(params.get("page_size", ["10"])[0])
    except (TypeError, ValueError):
        page_size = 10
    if page_size not in (10, 20, 50):
        page_size = 10
    try:
        page = max(1, int(params.get("page", ["1"])[0]))
    except (TypeError, ValueError):
        page = 1

    # This page is the current official catalog, never the historical table.
    rows = admin_units.units(con, active_only=True, communes_only=True)
    counts = {r[0]:r[1] for r in con.execute("SELECT ma_don_vi_hanh_chinh,COUNT(*) FROM user_admin_units GROUP BY ma_don_vi_hanh_chinh").fetchall()}
    rows = [r for r in rows if (not search or admin_units.normalize(search) in admin_units.normalize(r["code"] + " " + r["name"]))
            and (not level or r["level"] == level)]
    total_rows = len(rows)
    page_count = max(1, (total_rows + page_size - 1) // page_size)
    page = min(page, page_count)
    first_row = (page - 1) * page_size
    page_rows = rows[first_row:first_row + page_size]
    level_options = '<option value="">Tất cả cấp</option>' + ''.join(
        f'<option value="{k}" {"selected" if level == k else ""}>{admin_units.LEVELS[k]}</option>'
        for k in admin_units.CURRENT_LEVELS
    )
    page_size_options = ''.join(
        f'<option value="{size}" {"selected" if page_size == size else ""}>{size} dòng / trang</option>'
        for size in (10, 20, 50)
    )

    def listing_url(target_page):
        values = {"q": search, "level": level,
                  "page_size": str(page_size), "page": str(target_page)}
        return "/admin-units?" + urlencode({key: value for key, value in values.items() if value})

    def page_link(number):
        if number == page:
            return f'<span class="catalog-page-number active" aria-current="page">{number}</span>'
        return f'<a class="catalog-page-number" href="{esc(listing_url(number))}">{number}</a>'

    if page_count <= 7:
        page_links = list(range(1, page_count + 1))
    else:
        page_links = [1]
        if page > 3:
            page_links.append(None)
        page_links.extend(range(max(2, page - 1), min(page_count, page + 1) + 1))
        if page < page_count - 2:
            page_links.append(None)
        page_links.append(page_count)
    if total_rows:
        visible_from = first_row + 1
        visible_to = min(first_row + page_size, total_rows)
        pagination = (
            f'<div class="catalog-list-footer"><span class="catalog-list-summary">'
            f'Đang hiển thị <strong>{visible_from}–{visible_to}</strong> trên tổng <strong>{total_rows}</strong> bản ghi phù hợp.</span>'
            '<div class="catalog-pagination" aria-label="Phân trang danh mục">'
        )
        if page > 1:
            pagination += f'<a class="catalog-page-arrow" href="{esc(listing_url(page - 1))}">‹ Trước</a>'
        pagination += ''.join('<span class="catalog-page-ellipsis">…</span>' if number is None else page_link(number) for number in page_links)
        if page < page_count:
            pagination += f'<a class="catalog-page-arrow" href="{esc(listing_url(page + 1))}">Sau ›</a>'
        pagination += '</div></div>'
    else:
        pagination = '<div class="catalog-list-footer"><span class="catalog-list-summary">Đang hiển thị <strong>0</strong> trên tổng <strong>0</strong> bản ghi phù hợp.</span></div>'
    trs = ''
    for row in page_rows:
        path = '/admin-units/' + quote(row["code"], safe="")
        trs += f'''<tr><td>{esc(row['code'])}</td><td>{esc(row['name'])}</td><td>{esc(admin_units.LEVELS.get(row['level'],row['level']))}</td>
        <td>{esc(row['parent_code'])}</td><td>{counts.get(row['code'],0)}</td>
        <td><div class="actions"><a class="btn small" href="{path}/edit">Sửa</a></div></td></tr>'''
    return f'''<div class="container">{flash}<div class="page-head"><div><h1>Danh mục đơn vị hành chính</h1>
    <div class="subtitle">Danh mục chính thức hiện hành cho tài khoản, báo cáo tuần và OCOP.</div></div></div>
    <form method="get" class="card"><div class="grid"><div class="field"><label>Tìm mã hoặc tên</label><input name="q" value="{esc(search)}" placeholder="Mã hoặc tên đơn vị"></div>
    <div class="field"><label>Cấp hành chính</label><select name="level">{level_options}</select></div></div><button class="btn primary">Tìm kiếm / Lọc</button></form>
    <div class="card"><div class="catalog-list-heading"><div><strong>Danh sách đơn vị</strong><span>Lọc được {total_rows} bản ghi</span></div><form method="get" class="catalog-list-controls"><input type="hidden" name="q" value="{esc(search)}"><input type="hidden" name="level" value="{esc(level)}"><label for="catalog-page-size">Hiển thị</label><select id="catalog-page-size" name="page_size" onchange="this.form.submit()" aria-label="Số dòng mỗi trang">{page_size_options}</select></form></div><div class="table-wrap"><table class="summary-table catalog-table"><thead><tr><th>Mã đơn vị</th><th>Tên đơn vị</th><th>Cấp hành chính</th><th>Mã cấp trên</th><th>Số tài khoản liên kết</th><th>Thao tác</th></tr></thead>
    <tbody>{trs or '<tr><td colspan="6" class="empty">Không tìm thấy đơn vị phù hợp.</td></tr>'}</tbody></table></div>{pagination}</div></div>'''


def form(con, session, csrf, code, error="", data=None):
    admin_units.require_admin(con, session)
    row = admin_units.get_unit(con, code)
    if row is None or not row["active"] or row["level"] not in admin_units.CURRENT_LEVELS:
        raise admin_units.CatalogError("Không tìm thấy đơn vị.", 404)
    if data:
        row.update({k:data.get(k, "") for k in ("name", "level", "parent_code")})
    levels = ''.join(
        f'<option value="{k}" {"selected" if row["level"] == k else ""}>{admin_units.LEVELS[k]}</option>'
        for k in admin_units.CURRENT_LEVELS
    )
    parents = select_options(
        [r for r in admin_units.units(con, active_only=True) if r["code"] != code],
        row["parent_code"], "Không có cấp trên",
    )
    action = '/admin-units/' + quote(code, safe="") + '/edit'
    return f'''<div class="container"><div class="page-head"><h1>Sửa đơn vị hành chính</h1><a class="btn" href="/admin-units">Quay lại danh mục</a></div>
    {f'<div class="notice err">{esc(error)}</div>' if error else ''}
    <form method="post" class="card" action="{action}">{csrf}<div class="grid">
    <div class="field"><label>Mã đơn vị</label><input name="code" value="{esc(row['code'])}" required maxlength="10" pattern="[0-9]{{1,10}}" readonly aria-readonly="true"></div>
    <div class="field"><label>Tên đơn vị</label><input name="name" value="{esc(row['name'])}" required maxlength="255"></div>
    <div class="field"><label>Cấp hành chính</label><select name="level">{levels}</select></div>
    <div class="field"><label>Đơn vị cấp trên</label><select name="parent_code">{parents}</select></div></div>
    <button class="btn primary">Lưu thay đổi</button></form></div>'''
