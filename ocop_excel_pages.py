"""Small server-rendered pages for OCOP Excel import and lookup."""

from html import escape
from urllib.parse import quote


def _e(value):
    return escape("" if value is None else str(value), quote=True)


def _wrap(title, subtitle, content, helpers, actions=""):
    csrf = helpers.get("csrf", "")
    return title, (
        '<div class="container ocop-page"><div class="page-head"><div>'
        '<div class="ocop-breadcrumb"><a href="/ocop">OCOP</a></div>'
        f'<h1>{_e(title)}</h1><div class="subtitle">{_e(subtitle)}</div></div>'
        f'<div class="actions">{actions}</div></div>{content}</div>'
    )


def import_page(batches, helpers):
    rows = "".join(
        f'<tr><td>{_e(b["imported_at"])}</td><td>{_e(b["filename"])}</td>'
        f'<td>{_e(b["sheet_name"])}</td><td>{b["total_rows"]}</td>'
        f'<td>{b["imported_rows"]}</td><td>{b["updated_rows"]}</td></tr>' for b in batches
    ) or '<tr><td colspan="6"><div class="empty">Chưa có lần import nào.</div></td></tr>'
    content = (
        '<section class="card"><h2 class="ocop-section-heading">Chọn file OCOP</h2>'
        '<p class="muted">Upload workbook .xlsx. Hệ thống đọc sheet Loc, bỏ phần tổng hợp cuối sheet và cho xem trước trước khi ghi DB.</p>'
        '<form method="post" action="/ocop/import" enctype="multipart/form-data">'
        + helpers["csrf"] + '<div class="field"><label for="ocop-file">File Excel (.xlsx)</label>'
        '<input id="ocop-file" type="file" name="excel_file" accept=".xlsx" required></div>'
        '<button class="btn primary" type="submit">Kiểm tra và xem trước</button></form></section>'
        '<section class="card"><h2 class="ocop-section-heading">Lịch sử import</h2><div class="table-wrap"><table class="summary-table ocop-table">'
        '<thead><tr><th>Thời gian</th><th>File</th><th>Sheet</th><th>Dòng</th><th>Mới</th><th>Cập nhật</th></tr></thead><tbody>'
        + rows + '</tbody></table></div></section>'
    )
    return _wrap("Import dữ liệu OCOP", "Nhập danh sách chủ thể, sản phẩm và lịch sử công nhận từ Excel.", content, helpers, '<a class="btn" href="/ocop/products">Tra cứu sản phẩm</a>')


def preview_page(preview, helpers):
    rows = "".join(
        f'<tr><td>{r["excel_row"]}</td><td>{_e(r["unit_name"])}</td><td>{_e(r["entity_name"])}</td>'
        f'<td>{_e(r["product_name"])}</td><td>{_e(r["product_group"])}</td><td>{_e(r["current_star"] or "—")}</td></tr>'
        for r in preview["rows"][:100]
    )
    more = f'<p class="muted">Hiển thị 100/{preview["total_products"]} dòng đầu để kiểm tra.</p>' if preview["total_products"] > 100 else ""
    content = (
        f'<div class="notice info">File <strong>{_e(preview["filename"])}</strong> · sheet <strong>{_e(preview["sheet_name"])}</strong>. '
        f'{preview["total_products"]} sản phẩm, {preview["entity_names"]} chủ thể, {preview["unit_names"]} xã/phường, '
        f'{preview["second_recognitions"]} dòng có lần công nhận thứ hai.</div>'
        '<section class="card"><div class="table-wrap"><table class="summary-table ocop-table"><thead><tr><th>Dòng</th><th>Xã/phường</th><th>Chủ thể</th><th>Sản phẩm</th><th>Nhóm</th><th>Sao</th></tr></thead><tbody>'
        + rows + '</tbody></table></div>' + more + '</section>'
        '<form method="post" action="/ocop/import/confirm">' + helpers["csrf"]
        + '<button class="btn primary" type="submit">Import vào cơ sở dữ liệu</button> '
        + '<a class="btn" href="/ocop/import">Hủy</a></form>'
    )
    return _wrap("Xem trước import OCOP", "Kiểm tra dữ liệu trước khi tạo mã tạm và đồng bộ QĐ 5277.", content, helpers)
