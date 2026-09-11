"""Administrative catalog pages using the application's existing layout."""
from html import escape
from urllib.parse import parse_qs, quote
import admin_units


def esc(value):
    return escape(str(value or ""), quote=True)


def select_options(rows, selected="", blank="Chọn đơn vị"):
    result = f'<option value="">{esc(blank)}</option>'
    for row in rows:
        result += f'<option value="{esc(row["code"])}" {"selected" if row["code"] == selected else ""}>{esc(row["name"])} ({esc(row["code"])})</option>'
    return result


def account_fields(con, user=None):
    user = dict(user) if user else {"role":"unit"}
    mapping = con.execute("SELECT ma_don_vi_hanh_chinh FROM user_admin_units WHERE user_id=?", (user.get("id"),)).fetchone()
    selected = mapping[0] if mapping else ""
    options = select_options(admin_units.units(con, active_only=True, communes_only=True), selected)
    current = admin_units.get_unit(con, selected) if selected else None
    if current and not current["active"]:
        options += f'<option selected disabled value="{esc(selected)}">{esc(current["name"])} — đã ngưng; chọn địa bàn hoạt động</option>'
    unit = user["role"] == "unit"
    return f'''<div class="field" data-unit-field {"" if unit else "hidden"}>
      <label>Xã/phường đang hoạt động</label><select name="unit_code" {"required" if unit else "disabled"}>{options}</select></div>
      <div class="field" data-office-field {"hidden" if unit else ""}><label>Tên cơ quan</label>
      <input name="unit_name" value="{esc(user.get('unit_name') if not unit else 'Chi cục')}" {"disabled" if unit else "required"}></div>'''


def listing(con, session, query, csrf, flash=""):
    admin_units.require_admin(con, session)
    params = parse_qs(query)
    search = params.get("q", [""])[0].strip()
    level = params.get("level", [""])[0]
    status = params.get("active", [""])[0]
    rows = admin_units.units(con)
    counts = {r[0]:r[1] for r in con.execute("SELECT ma_don_vi_hanh_chinh,COUNT(*) FROM user_admin_units GROUP BY ma_don_vi_hanh_chinh").fetchall()}
    rows = [r for r in rows if (not search or admin_units.normalize(search) in admin_units.normalize(r["code"] + " " + r["name"]))
            and (not level or r["level"] == level) and (status not in ("0","1") or bool(r["active"]) == (status == "1"))]
    level_options = '<option value="">Tất cả cấp</option>' + ''.join(f'<option value="{k}" {"selected" if level == k else ""}>{v}</option>' for k,v in admin_units.LEVELS.items())
    status_options = ''.join(f'<option value="{k}" {"selected" if status == k else ""}>{v}</option>' for k,v in (("","Tất cả trạng thái"),("1","Hoạt động"),("0","Ngưng hoạt động")))
    trs = ''
    for row in rows:
        path = '/admin-units/' + quote(row["code"], safe="")
        trs += f'''<tr><td>{esc(row['code'])}</td><td>{esc(row['name'])}</td><td>{esc(admin_units.LEVELS.get(row['level'],row['level']))}</td>
        <td>{esc(row['parent_code'])}</td><td>{'Hoạt động' if row['active'] else 'Ngưng hoạt động'}</td><td>{counts.get(row['code'],0)}</td>
        <td><div class="actions"><a class="btn small" href="{path}/edit">Sửa</a><form method="post" action="{path}/{'deactivate' if row['active'] else 'activate'}">{csrf}
        <button class="btn small warn">{'Ngưng hoạt động' if row['active'] else 'Kích hoạt lại'}</button></form></div></td></tr>'''
    return f'''<div class="container">{flash}<div class="page-head"><div><h1>Danh mục đơn vị hành chính</h1>
    <div class="subtitle">Danh mục chung cho tài khoản, báo cáo tuần và OCOP.</div></div><a class="btn primary" href="/admin-units/new">Thêm đơn vị</a></div>
    <form method="get" class="card"><div class="grid"><div class="field"><label>Tìm mã hoặc tên</label><input name="q" value="{esc(search)}" placeholder="Mã hoặc tên đơn vị"></div>
    <div class="field"><label>Cấp hành chính</label><select name="level">{level_options}</select></div><div class="field"><label>Trạng thái</label><select name="active">{status_options}</select></div></div><button class="btn primary">Tìm kiếm / Lọc</button></form>
    <div class="card"><p>{len(rows)} đơn vị</p><div class="table-wrap"><table class="summary-table"><thead><tr><th>Mã đơn vị</th><th>Tên đơn vị</th><th>Cấp hành chính</th><th>Mã cấp trên</th><th>Trạng thái</th><th>Số tài khoản liên kết</th><th>Thao tác</th></tr></thead>
    <tbody>{trs or '<tr><td colspan="7">Không tìm thấy đơn vị.</td></tr>'}</tbody></table></div></div></div>'''


def form(con, session, csrf, code=None, error="", data=None):
    admin_units.require_admin(con,session)
    row = admin_units.get_unit(con,code) if code else {"code":"", "name":"", "level":"xa", "parent_code":"", "active":True}
    if row is None:
        raise admin_units.CatalogError("Không tìm thấy đơn vị.",404)
    if data:
        row.update({k:data.get(k, "") for k in ("name","level","parent_code")})
        row["active"] = data.get("active") == "1"
        if code is None:
            row["code"] = data.get("code", "")
    levels = ''.join(f'<option value="{k}" {"selected" if row["level"] == k else ""}>{v}</option>' for k,v in admin_units.LEVELS.items())
    parents = select_options([r for r in admin_units.units(con) if r["code"] != code], row["parent_code"], "Không có cấp trên")
    action = '/admin-units/' + quote(code,safe="") + '/edit' if code else '/admin-units/new'
    return f'''<div class="container"><div class="page-head"><h1>{'Sửa' if code else 'Thêm'} đơn vị hành chính</h1><a class="btn" href="/admin-units">Quay lại danh mục</a></div>
    {f'<div class="notice err">{esc(error)}</div>' if error else ''}
    <form method="post" class="card" action="{action}">{csrf}<div class="grid">
    <div class="field"><label>Mã đơn vị</label><input name="code" value="{esc(row['code'])}" required maxlength="10" pattern="[0-9]{{1,10}}" {"readonly" if code else ""}></div>
    <div class="field"><label>Tên đơn vị</label><input name="name" value="{esc(row['name'])}" required maxlength="255"></div>
    <div class="field"><label>Cấp hành chính</label><select name="level">{levels}</select></div>
    <div class="field"><label>Đơn vị cấp trên</label><select name="parent_code">{parents}</select></div>
    <div class="field"><label><input type="checkbox" name="active" value="1" {'checked' if row['active'] else ''}> Hoạt động</label></div></div>
    <button class="btn primary">Lưu đơn vị</button></form></div>'''
