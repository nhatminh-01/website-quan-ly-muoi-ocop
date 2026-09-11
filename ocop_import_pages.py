"""Server-rendered UI for historical OCOP Excel import and recognition history."""
from __future__ import annotations

from html import escape
from urllib.parse import parse_qs, urlencode

import ocop_import
import ocop_services
from permissions import is_chi_cuc_user


def _e(value):
    return escape("" if value is None else str(value), quote=True)


def _one(params, key, default=""):
    value = params.get(key, [default])
    if isinstance(value, (list, tuple)):
        value = value[0] if value else default
    return str(value or "").strip()


def _status_badge(status):
    label = {"published": "Đã đồng bộ", "committed": "Đã lưu staging"}.get(status, status)
    return f'<span class="ocop-status ocop-status-{"eligible" if status == "published" else "checking"}">{_e(label)}</span>'


def import_page(session, con, helpers):
    if not is_chi_cuc_user(session):
        return "403", '<div class="container"><div class="notice err">Chỉ tài khoản Chi cục được import dữ liệu OCOP.</div></div>', 403
    csrf = helpers["csrf_input"](session)
    flash = helpers["take_flash"](session)
    batches = ocop_import.list_batches(con)
    rows = "".join(
        f"<tr><td>{b['id']}</td><td>{_e(b['filename'])}</td><td>{_e(b['sheet_name'])}</td>"
        f"<td>{b['total_rows']}</td><td>{b['warning_rows']}</td><td>{b['error_rows']}</td>"
        f"<td>{_status_badge(b['status'])}</td><td>{_e(b['username'])}</td><td>{_e(b['imported_at'])}</td></tr>"
        for b in batches
    ) or '<tr><td colspan="9" class="empty">Chưa có đợt import OCOP.</td></tr>'
    body = f"""
    <div class="container ocop-page">{flash}
      <div class="page-head"><div><div class="ocop-breadcrumb"><a href="/ocop">OCOP</a></div>
        <h1>Import Excel OCOP</h1><div class="subtitle">Nạp dữ liệu lịch sử từ CCPTNT OCOP.xlsx theo quy trình xem trước → kiểm tra → xác nhận.</div></div>
        <div class="actions"><a class="btn" href="/ocop/recognitions">Lịch sử công nhận</a></div></div>
      <div class="notice info"><b>Nguyên tắc an toàn:</b> hệ thống giữ nguyên dữ liệu nguồn trong staging, không tự tạo mã xã/phường và không tự sửa mâu thuẫn hạng sao. Địa bàn chưa có mã chính thức sẽ được báo lỗi để bổ sung trong Danh mục đơn vị hành chính.</div>
      <form class="card js-loading-form" method="post" action="/ocop/import" enctype="multipart/form-data">
        {csrf}
        <div class="grid">
          <div class="field"><label>File Excel OCOP (.xlsx)</label><input type="file" name="excel_file" accept=".xlsx" required></div>
          <div class="field"><label>Tên sheet</label><input name="sheet_name" value="Loc" maxlength="255" placeholder="Loc"></div>
        </div>
        <button class="btn primary" type="submit" style="margin-top:16px">Xem trước và kiểm tra</button>
      </form>
      <section class="card"><div class="ocop-detail-heading"><h2 class="ocop-section-heading">Lịch sử import</h2></div>
        <div class="table-wrap"><table class="summary-table"><thead><tr><th>ID</th><th>File</th><th>Sheet</th><th>Dòng</th><th>Cảnh báo</th><th>Lỗi</th><th>Trạng thái</th><th>Người import</th><th>Thời gian</th></tr></thead><tbody>{rows}</tbody></table></div>
      </section>
    </div>"""
    return "Import Excel OCOP", body, 200


def preview_page(session, preview, helpers):
    if not is_chi_cuc_user(session):
        return "403", '<div class="container"><div class="notice err">Chỉ tài khoản Chi cục được import dữ liệu OCOP.</div></div>', 403
    csrf = helpers["csrf_input"](session)
    unknown = preview.get("unknown_units", [])
    unknown_html = ""
    if unknown:
        chips = "".join(f'<span class="ocop-status ocop-status-returned">{_e(name)}</span> ' for name in unknown[:80])
        more = f"<p class='muted'>Còn {len(unknown)-80} địa bàn khác.</p>" if len(unknown) > 80 else ""
        unknown_html = f'''<section class="card"><div class="ocop-detail-heading"><h2 class="ocop-section-heading">Địa bàn chưa ánh xạ ({len(unknown)})</h2><a class="btn small" href="/admin-units">Mở danh mục đơn vị</a></div><p>{chips}</p>{more}</section>'''

    issue_rows = []
    for row in preview["rows"]:
        if row["status"] == "valid":
            continue
        messages = row["errors"] + row["warnings"]
        issue_rows.append(
            f"<tr><td>{row['excel_row']}</td><td>{_e(row['source_tt'])}</td><td>{_e(row['canonical']['product']['name'])}</td>"
            f"<td>{_e(row['source_unit_name'])}</td><td>{_e(row['status'])}</td><td>{'<br>'.join(_e(x) for x in messages)}</td></tr>"
        )
        if len(issue_rows) >= 100:
            break
    issue_table = "".join(issue_rows) or '<tr><td colspan="6" class="empty">Không có lỗi/cảnh báo.</td></tr>'
    can_publish = preview["error_rows"] == 0
    publish_button = (
        '<button class="btn primary" type="submit" name="mode" value="publish">Đồng bộ vào OCOP</button>'
        if can_publish else
        '<button class="btn primary" type="button" disabled title="Cần xử lý hết dòng lỗi trước khi đồng bộ">Đồng bộ vào OCOP</button>'
    )
    body = f"""
    <div class="container ocop-page">
      <div class="page-head"><div><div class="ocop-breadcrumb"><a href="/ocop">OCOP</a> / <a href="/ocop/import">Import</a></div>
        <h1>Xem trước import OCOP</h1><div class="subtitle">{_e(preview['filename'])} · sheet {_e(preview['sheet_name'])}</div></div>
        <div class="actions"><a class="btn" href="/ocop/import">Chọn lại file</a></div></div>
      <div class="ocop-metrics">
        <div class="ocop-metric"><span>Sản phẩm nguồn</span><strong>{preview['product_count']}</strong><small>{preview['entity_count']} chủ thể</small></div>
        <div class="ocop-metric"><span>Lịch sử công nhận</span><strong>{preview['recognition_count']}</strong><small>Lần 1 + lần 2/nâng hạng</small></div>
        <div class="ocop-metric"><span>Địa bàn đã ánh xạ</span><strong>{preview['mapped_unit_count']}/{preview['source_unit_count']}</strong><small>Theo danh mục dùng chung</small></div>
        <div class="ocop-metric"><span>Dòng cần xử lý</span><strong>{preview['error_rows']}</strong><small>{preview['warning_rows']} dòng cảnh báo</small></div>
      </div>
      {unknown_html}
      <section class="card"><h2 class="ocop-section-heading">Lỗi và cảnh báo (tối đa 100 dòng)</h2>
        <div class="table-wrap"><table class="summary-table"><thead><tr><th>Dòng Excel</th><th>TT</th><th>Sản phẩm</th><th>Địa bàn nguồn</th><th>Mức</th><th>Nội dung</th></tr></thead><tbody>{issue_table}</tbody></table></div>
      </section>
      <form class="card actions" method="post" action="/ocop/import/confirm">{csrf}
        <button class="btn" type="submit" name="mode" value="stage_only">Chỉ lưu staging để đối chiếu</button>
        {publish_button}
      </form>
      <div class="notice info">Lưu staging cho phép giữ nguyên toàn bộ 1:1 dữ liệu Excel kể cả khi chưa có mã địa bàn. Nút “Đồng bộ vào OCOP” chỉ hoạt động khi không còn lỗi và sẽ cập nhật Chủ thể, Sản phẩm, Lịch sử công nhận và PTNT_OCOP hiện hành trong cùng một transaction.</div>
    </div>"""
    return "Xem trước import OCOP", body, 200


def recognitions_page(session, con, query, helpers):
    params = parse_qs(str(query or ""))
    filters = {key: _one(params, key) for key in ("q", "unit", "year")}
    rows = ocop_import.list_recognitions(con, session, filters)
    total = len(rows)
    try:
        page = max(1, int(_one(params, "page", "1")))
    except ValueError:
        page = 1
    page_size = 100
    pages = max(1, (total + page_size - 1) // page_size)
    if page > pages:
        page = pages
    shown = rows[(page - 1) * page_size:page * page_size]
    unit_options = ""
    if is_chi_cuc_user(session):
        options = ['<option value="">Tất cả đơn vị</option>']
        for item in ocop_services.unit_options(con, session):
            selected = " selected" if item["code"] == filters["unit"] else ""
            options.append(f'<option value="{_e(item["code"])}"{selected}>{_e(item["name"])}</option>')
        unit_options = f'<div class="field"><label>Đơn vị</label><select name="unit">{"".join(options)}</select></div>'
    table_rows = "".join(
        f"<tr><td>{_e(r['unit_name'])}</td><td><a href='/ocop/products/{r['product_id']}'>{_e(r['ten_san_pham'])}</a></td>"
        f"<td>{_e(r['entity_name'])}</td><td>{r['recognition_sequence']}</td><td>{_e(r['evaluation_type'])}</td>"
        f"<td>{r['star_rank']} sao</td><td>{_e(r['recognition_date'] or '')}</td><td>{r['recognition_year']}</td>"
        f"<td>{_e(r['decision_number'])}</td><td>{_e(r['decision_authority'])}</td><td>{_e(r['expiry_date'] or '')}</td>"
        f"<td>{'<span class=\"ocop-status ocop-status-eligible\">Hiện hành</span>' if r['is_current'] else ''}</td></tr>"
        for r in shown
    ) or '<tr><td colspan="12" class="empty">Chưa có lịch sử công nhận OCOP.</td></tr>'
    nav = []
    for target, label in ((page - 1, "← Trước"), (page + 1, "Sau →")):
        if 1 <= target <= pages:
            q = {k: v for k, v in filters.items() if v}
            q["page"] = target
            nav.append(f'<a class="btn small" href="/ocop/recognitions?{urlencode(q)}">{label}</a>')
    import_action = '<a class="btn primary" href="/ocop/import">Import Excel OCOP</a>' if is_chi_cuc_user(session) else ""
    body = f"""
    <div class="container ocop-page">{helpers['take_flash'](session)}
      <div class="page-head"><div><div class="ocop-breadcrumb"><a href="/ocop">OCOP</a></div><h1>Lịch sử công nhận OCOP</h1>
        <div class="subtitle">Lưu riêng từng lần công nhận/đánh giá lại/nâng hạng; không ghi đè lịch sử.</div></div><div class="actions">{import_action}</div></div>
      <div class="card"><form class="toolbar" method="get">
        <div class="field"><label>Từ khóa</label><input name="q" value="{_e(filters['q'])}" placeholder="Sản phẩm, chủ thể, số quyết định"></div>
        {unit_options}<div class="field"><label>Năm công nhận</label><input name="year" type="number" min="1900" max="9999" value="{_e(filters['year'])}"></div>
        <button class="btn primary">Lọc dữ liệu</button><a class="btn" href="/ocop/recognitions">Xóa lọc</a>
      </form></div>
      <div class="card"><div class="ocop-detail-heading"><h2 class="ocop-section-heading">{total} lần công nhận</h2><span class="muted">Trang {page}/{pages}</span></div>
        <div class="table-wrap"><table class="summary-table"><thead><tr><th>Đơn vị</th><th>Sản phẩm</th><th>Chủ thể</th><th>Lần</th><th>Loại</th><th>Hạng</th><th>Ngày công nhận</th><th>Năm</th><th>Số QĐ</th><th>Cơ quan QĐ</th><th>Hết hạn</th><th>Trạng thái</th></tr></thead><tbody>{table_rows}</tbody></table></div>
        <div class="actions" style="margin-top:12px">{''.join(nav)}</div>
      </div>
    </div>"""
    return "Lịch sử công nhận OCOP", body, 200


def product_history_section(con, session, product_id):
    try:
        _, rows = ocop_import.recognitions_for_product(con, session, product_id)
    except Exception:
        return ""
    if not rows:
        return ""
    table_rows = "".join(
        f"<tr><td>{r['recognition_sequence']}</td><td>{_e(r['evaluation_type'])}</td><td>{r['star_rank']} sao</td>"
        f"<td>{_e(r['recognition_date'] or '')}</td><td>{r['recognition_year']}</td><td>{_e(r['decision_number'])}</td>"
        f"<td>{_e(r['decision_authority'])}</td><td>{_e(r['expiry_date'] or '')}</td>"
        f"<td>{'<span class=\"ocop-status ocop-status-eligible\">Hiện hành</span>' if r['is_current'] else ''}</td></tr>"
        for r in rows
    )
    return f'''<section class="card"><div class="ocop-detail-heading"><h2 class="ocop-section-heading">LỊCH SỬ CÔNG NHẬN</h2><a class="btn small" href="/ocop/recognitions">Tra cứu toàn bộ</a></div><div class="table-wrap"><table class="summary-table"><thead><tr><th>Lần</th><th>Loại</th><th>Hạng</th><th>Ngày công nhận</th><th>Năm</th><th>Số QĐ</th><th>Cơ quan QĐ</th><th>Hết hạn</th><th>Trạng thái</th></tr></thead><tbody>{table_rows}</tbody></table></div></section>'''
