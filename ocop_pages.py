"""Vietnamese server-rendered pages for OCOP foundation and dynamic criteria."""

from datetime import date, datetime
from html import escape
from urllib.parse import parse_qs, quote, urlencode
import re

import ocop_services as svc
from permissions import is_chi_cuc_user


STATUS_LABELS = {
    "active": "Đang sử dụng",
    "archived": "Ngừng sử dụng",
    "draft": "Bản nháp",
    "submitted": "Đã gửi",
    "checking": "Đang kiểm tra",
    "returned": "Cần bổ sung",
    "eligible": "Hồ sơ hợp lệ",
    "scoring": "Đang đánh giá",
    "completed": "Đã hoàn tất",
    "cancelled": "Đã hủy",
}
EVALUATION_LABELS = {
    "new": "Đánh giá lần đầu",
    "re_evaluation": "Đánh giá lại",
    "upgrade": "Đánh giá nâng hạng",
}
REVIEW_LABELS = {
    "create": "Tạo hồ sơ",
    "edit": "Cập nhật hồ sơ",
    "created": "Tạo hồ sơ",
    "updated": "Cập nhật hồ sơ",
    "submitted": "Gửi hồ sơ",
    "submit": "Gửi hồ sơ",
    "checking": "Bắt đầu kiểm tra",
    "start-review": "Bắt đầu kiểm tra",
    "request_revision": "Yêu cầu bổ sung",
    "returned": "Yêu cầu bổ sung",
    "return": "Yêu cầu bổ sung",
    "resubmitted": "Gửi lại hồ sơ",
    "eligible": "Xác nhận hồ sơ hợp lệ",
    "cancelled": "Hủy hồ sơ",
    "cancel": "Hủy hồ sơ",
}
KINDS = {
    "entities": ("Chủ thể OCOP", "chủ thể", "Tạo chủ thể"),
    "products": ("Sản phẩm OCOP", "sản phẩm", "Tạo sản phẩm"),
    "applications": ("Hồ sơ đánh giá OCOP", "hồ sơ", "Tạo hồ sơ"),
}


def _number(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _phone_href(value):
    """Return a safe tel target while keeping the source formatting visible."""
    normalized = re.sub(r"[\s().-]", "", str(value or "").strip())
    return normalized if re.fullmatch(r"\+?\d{6,20}", normalized) else ""


def _expiry_band(days):
    """Return presentation metadata for an expiring product row."""
    try:
        days = int(days)
    except (TypeError, ValueError):
        return "", ""
    if days <= 30:
        return "critical", "≤ 30 ngày"
    if days <= 60:
        return "soon", "31–60 ngày"
    return "later", "> 60 ngày"


def format_ocop_date(value):
    """Format date-like OCOP values for the UI without changing stored data."""
    if value in (None, ""):
        return "—"
    if isinstance(value, datetime):
        return value.date().strftime("%d/%m/%Y")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    text = str(value).strip()
    if not text:
        return "—"
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        try:
            return date.fromisoformat(text[:10]).strftime("%d/%m/%Y")
        except ValueError:
            pass
    return text


def _return_context(query):
    values = query if isinstance(query, dict) else parse_qs(str(query or "").lstrip("?"))
    value = values.get("from", "")
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    value = str(value).strip()
    return value if value in {"expiry", "catalog"} else ""


def _filters(query):
    if isinstance(query, dict):
        values = query
    else:
        values = parse_qs(str(query or "").lstrip("?"))
    result = {}
    for key in ("q", "unit", "year", "status", "group", "star", "category",
                "contact", "remaining", "page", "page_size"):
        value = values.get(key, "")
        if isinstance(value, (list, tuple)):
            value = value[0] if value else ""
        if value is not None and str(value).strip():
            result[key] = str(value).strip()
    return result


def render(path, query, session, con, helpers):
    """Return (title, body) for a recognized GET route, otherwise None.

    Permission and data access checks stay in ocop_services. Pages add no SQL
    and every mutation is a separate POST request with a CSRF token.
    """
    clean_path = str(path or "").rstrip("/") or "/"
    if clean_path != "/ocop" and not re.fullmatch(
        r"/ocop/(entities|products|applications)(?:/(new|\d+)(?:/edit)?)?|/ocop/criteria(?:/\d+)?|/ocop/expiry-alerts",
        clean_path,
    ):
        return None
    page = _Pages(session, con, helpers, _filters(query), _return_context(query))
    if clean_path == "/ocop":
        return page.catalog_page()
    if clean_path == "/ocop/expiry-alerts":
        return page.expiry_alerts()
    parts = clean_path.strip("/").split("/")
    kind = parts[1]
    if kind == "criteria":
        if len(parts) == 2:
            return page.criteria_catalog()
        return page.criteria_detail(int(parts[2]))
    if len(parts) == 2:
        return page.list_page(kind)
    if parts[2] == "new":
        if len(parts) != 3:
            return None
        return page.form_page(kind)
    record = dict(getattr(svc, "get_" + kind[:-1] if kind != "entities" else "get_entity")(
        con, session, int(parts[2])
    ))
    if len(parts) == 4:
        return page.form_page(kind, record)
    return page.detail_page(kind, record)


class _Pages:
    def __init__(self, session, con, helpers, filters, return_context=""):
        self.session = session
        self.con = con
        self.filters = filters
        self.return_context = return_context
        self.admin = is_chi_cuc_user(session)
        self.scope = svc.get_scope(con, session)
        self.escape = helpers.get("esc") or (lambda value: escape(str(value or ""), quote=True))
        self.csrf = helpers["csrf_input"](session)
        self.form_data = helpers.get("form_data")
        self.error = helpers.get("error")

    def e(self, value):
        return self.escape("" if value is None else value)

    def link(self, href, label, tone=""):
        return f'<a class="btn {self.e(tone)}" href="{self.e(href)}">{self.e(label)}</a>'

    def url(self, kind, record=None, action=None):
        path = "/ocop/" + kind
        if record is not None:
            path += "/" + quote(str(record["id"]), safe="")
        if action:
            path += "/" + action
        return path

    def wrap(self, title, subtitle, content, actions=""):
        head = (
            '<div class="page-head"><div>'
            f'<div class="ocop-breadcrumb"><a href="/ocop">OCOP</a></div>'
            f'<h1>{self.e(title)}</h1><div class="subtitle">{self.e(subtitle)}</div>'
            f'</div><div class="actions">{actions}</div></div>'
        )
        return title, '<div class="container ocop-page">' + head + content + "</div>"

    def badge(self, status):
        known = status if status in STATUS_LABELS else "draft"
        return (
            f'<span class="ocop-status ocop-status-{known}">'
            f'{self.e(STATUS_LABELS.get(status, status or "Chưa cập nhật"))}</span>'
        )

    def hidden_revision(self, kind, record):
        if not record:
            return ""
        field = "revision" if kind == "applications" else "updated_at"
        return f'<input type="hidden" name="{field}" value="{self.e(record.get(field, ""))}">'

    def post_button(self, kind, record, action, label, tone="", extra=""):
        return (
            f'<form class="ocop-inline-form" method="post" action="{self.e(self.url(kind, record, action))}">'
            + self.csrf + self.hidden_revision(kind, record) + extra
            + f'<button type="submit" class="btn {self.e(tone)}">{self.e(label)}</button></form>'
        )

    def input(self, name, label, value="", typ="text", required=False, attrs=""):
        req = " required" if required else ""
        mark = ' <span class="ocop-required" aria-hidden="true">*</span>' if required else ""
        return (
            f'<div class="field"><label for="ocop-{name}">{self.e(label)}{mark}</label>'
            f'<input id="ocop-{name}" name="{name}" type="{typ}" value="{self.e(value)}"{req} {attrs}></div>'
        )

    def textarea(self, name, label, value="", required=False):
        req = " required" if required else ""
        return (
            f'<div class="field ocop-full"><label for="ocop-{name}">{self.e(label)}</label>'
            f'<textarea id="ocop-{name}" name="{name}" maxlength="5000"{req}>{self.e(value)}</textarea></div>'
        )

    def select(self, name, label, options, selected="", required=False, empty="Chọn…"):
        req = " required" if required else ""
        choices = f'<option value="">{self.e(empty)}</option>' if empty is not None else ""
        for value, text in options:
            picked = " selected" if str(value) == str(selected) else ""
            choices += f'<option value="{self.e(value)}"{picked}>{self.e(text)}</option>'
        return (
            f'<div class="field"><label for="ocop-{name}">{self.e(label)}</label>'
            f'<select id="ocop-{name}" name="{name}"{req}>{choices}</select></div>'
        )

    def unit_field(self, selected="", filtering=False):
        options = [(r["code"], r["name"]) for r in svc.unit_options(self.con, self.session)]
        if filtering:
            if not self.admin:
                return ""
            return self.select("unit", "Đơn vị", options, selected, empty="Tất cả đơn vị")
        if self.admin:
            return self.select("ma_don_vi_hanh_chinh", "Xã/phường", options, selected, True)
        selected = self.scope
        label = next((name for code, name in options if str(code) == str(selected)), selected)
        return (
            '<div class="field"><label for="ocop-unit-display">Xã/phường</label>'
            f'<input id="ocop-unit-display" value="{self.e(label)}" readonly>'
            f'<input type="hidden" name="ma_don_vi_hanh_chinh" value="{self.e(selected)}"></div>'
        )

    def filter_bar(self, kind=None):
        f = self.filters
        path = "/ocop" if kind is None else self.url(kind)
        fields = ""
        if kind:
            fields += self.input("q", "Từ khóa", f.get("q", ""), attrs='maxlength="200" placeholder="Tên, mã hoặc chủ thể…"')
        if kind == "criteria":
            categories = [(r["name"], r["name"]) for r in svc.criteria_categories(self.con, self.session)]
            fields += self.select("category", "Nhóm sản phẩm lớn", categories, f.get("category", ""), empty="Tất cả nhóm")
        else:
            fields += self.unit_field(f.get("unit", ""), True)
        if kind in (None, "applications"):
            fields += self.input("year", "Năm đánh giá", f.get("year", ""), "number", attrs='min="2000" max="2100" step="1" placeholder="Tất cả năm"')
        if kind == "products":
            fields += self.input("group", "Nhóm sản phẩm", f.get("group", ""), attrs='maxlength="100" placeholder="Tất cả nhóm"')
            fields += self.select("star", "Hạng sao", [("3", "3 sao"), ("4", "4 sao"), ("5", "5 sao")], f.get("star", ""), empty="Tất cả hạng")
        if kind and kind != "criteria":
            states = ("active", "archived") if kind != "applications" else (
                "draft", "submitted", "checking", "returned", "eligible", "cancelled"
            )
            fields += self.select("status", "Trạng thái", [(s, STATUS_LABELS[s]) for s in states], f.get("status", ""), empty="Tất cả trạng thái")
        return (
            f'<div class="card"><form class="toolbar" action="{path}" method="get">{fields}'
            f'<button type="submit" class="btn primary">Lọc dữ liệu</button>{self.link(path, "Xóa lọc")}</form></div>'
        )

    def pagination(self, kind, result):
        page = max(1, _number(result.get("page"), 1))
        pages = max(1, _number(result.get("pages"), 1))
        total = max(0, _number(result.get("total")))
        size = max(1, _number(result.get("page_size"), 20))
        start = (page - 1) * size + 1 if total else 0
        end = min(page * size, total)
        links = []
        for target, label in ((page - 1, "← Trước"), (page + 1, "Sau →")):
            if 1 <= target <= pages:
                values = dict(self.filters, page=target)
                links.append(self.link(self.url(kind) + "?" + urlencode(values), label, "small"))
        return (
            '<nav class="ocop-pagination" aria-label="Phân trang">'
            f'<span class="muted">Hiển thị {start}–{end} / {total} · Trang {page}/{pages}</span>'
            '<div class="actions">' + "".join(links) + "</div></nav>"
        )

    def catalog_page(self):
        """Primary OCOP screen: a read-only business catalogue and export."""
        result = svc.list_products(self.con, self.session, self.filters)
        rows = [dict(r) for r in result.get("items", [])]
        export_filters = {k: v for k, v in self.filters.items() if k not in ("page", "page_size")}
        export_query = urlencode(export_filters)
        unit_field = self.unit_field(self.filters.get("unit", ""), True)
        star_options = self.select("star", "Hạng sao", [("3", "3 sao"), ("4", "4 sao"), ("5", "5 sao")], self.filters.get("star", ""), empty="Tất cả hạng")
        filter_form = (
            '<div class="card"><form class="toolbar" action="/ocop" method="get">'
            f'<div class="field"><label>Từ khóa</label><input name="q" value="{self.e(self.filters.get("q", ""))}" maxlength="200" placeholder="Tên sản phẩm hoặc chủ thể…"></div>'
            f'{unit_field}{star_options}'
            f'<div class="field"><label>Nhóm sản phẩm</label><input name="group" value="{self.e(self.filters.get("group", ""))}" maxlength="100" placeholder="Tất cả nhóm"></div>'
            '<button type="submit" class="btn primary">Tra cứu</button><a class="btn" href="/ocop">Xóa lọc</a></form></div>'
        )
        rendered = []
        for row in rows:
            rank = row.get("recognition_star") or row.get("current_star")
            detail_href = self.url("products", row) + "?from=catalog"
            rendered.append(
                '<tr>'
                f'<td>{self.e(row.get("unit_name"))}</td>'
                f'<td><a href="{self.e(detail_href)}"><strong>{self.e(row.get("name"))}</strong></a></td>'
                f'<td>{self.e(row.get("entity_name"))}</td>'
                f'<td>{self.e(row.get("product_group"))}</td><td>{self.e((str(rank) + " sao") if rank else "")}</td>'
                f'<td>{self.e(format_ocop_date(row.get("latest_recognition_date")))}</td><td>{self.e(format_ocop_date(row.get("latest_expiry_date")))}</td>'
                f'<td><a class="btn small" href="{self.e(detail_href)}">Chi tiết</a></td></tr>'
            )
        table_rows = ''.join(rendered) or '<tr><td colspan="8" class="empty">Chưa có sản phẩm OCOP phù hợp.</td></tr>'
        page = int(result.get("page") or 1)
        pages = int(result.get("pages") or 1)
        page_links = []
        if page > 1:
            page_links.append(f'<a class="btn small" href="/ocop?{urlencode({**export_filters, "page": page - 1})}">← Trước</a>')
        if page < pages:
            page_links.append(f'<a class="btn small" href="/ocop?{urlencode({**export_filters, "page": page + 1})}">Sau →</a>')
        pagination = f'<div class="ocop-pagination"><span class="muted">{result.get("total", 0)} sản phẩm · Trang {page}/{pages}</span><div class="actions">{"".join(page_links)}</div></div>'
        actions = '<a class="btn ok" href="/ocop/export.xlsx' + (('?' + export_query) if export_query else '') + '">Xuất Excel</a>'
        if self.admin:
            actions = '<a class="btn primary" href="/ocop/import">Import dữ liệu OCOP</a>' + actions
        content = (
            filter_form
            + '<div class="card"><div class="ocop-detail-heading"><h2 class="ocop-section-heading">Danh mục sản phẩm OCOP</h2>'
            + f'<span class="muted">{result.get("total", 0)} sản phẩm</span></div>'
            + '<div class="table-wrap"><table class="summary-table ocop-table ocop-catalog-table"><thead><tr>'
            + '<th>Xã/phường</th><th>Tên sản phẩm</th><th>Chủ thể</th><th>Nhóm sản phẩm</th><th>Hạng sao</th><th>Ngày công nhận</th><th>Ngày hết hạn</th><th>Chi tiết</th>'
            + '</tr></thead><tbody>' + table_rows + '</tbody></table></div>' + pagination + '</div>'
        )
        return self.wrap("Tra cứu OCOP", "Tra cứu sản phẩm theo địa bàn, chủ thể, nhóm sản phẩm và hạng sao.", content, actions)

    def contact_markup(self, row):
        if not row.get("has_contact"):
            return '<div class="ocop-contact"><span class="ocop-contact-empty">Chưa có thông tin liên hệ</span></div>'

        parts = []
        representative = str(row.get("representative_name") or "").strip()
        if representative:
            parts.append('<span><b>Người đại diện:</b> ' + self.e(representative) + '</span>')
        phone = str(row.get("phone") or "").strip()
        if phone:
            phone_href = _phone_href(phone)
            phone_html = self.e(phone)
            if phone_href:
                phone_html = '<a href="' + self.e("tel:" + phone_href) + '">' + phone_html + '</a>'
            parts.append('<span><b>Số điện thoại:</b> ' + phone_html + '</span>')
        email = str(row.get("email") or "").strip()
        if email:
            email_href = quote(email, safe="@._+-")
            parts.append('<span><b>Email:</b> <a href="' + self.e("mailto:" + email_href) + '">' + self.e(email) + '</a></span>')
        return '<div class="ocop-contact">' + ''.join(parts) + '</div>'

    def expiry_alerts(self):
        rows = [dict(row) for row in svc.get_expiring_ocop_products(
            self.con, self.session, self.filters
        )]
        f = self.filters
        fields = (
            self.input("q", "Từ khóa", f.get("q", ""),
                       attrs='maxlength="200" placeholder="Tên sản phẩm hoặc chủ thể…"')
            + self.unit_field(f.get("unit", ""), True)
            + self.select("star", "Hạng sao", [("3", "3 sao"), ("4", "4 sao"), ("5", "5 sao")],
                          f.get("star", ""), empty="Tất cả hạng")
            + self.select("remaining", "Thời gian còn lại", [
                ("up_to_1_month", "Dưới 1 tháng"),
                ("up_to_2_months", "Dưới 2 tháng"),
                ("up_to_3_months", "Dưới 3 tháng"),
            ], f.get("remaining", ""), empty="Tất cả dưới 3 tháng")
            + self.select("contact", "Thông tin liên hệ", [
                ("has", "Có thông tin liên hệ"),
                ("none", "Chưa có thông tin liên hệ"),
            ], f.get("contact", ""), empty="Tất cả")
        )
        filter_form = (
            '<div class="card"><form class="toolbar" action="/ocop/expiry-alerts" method="get">'
            + fields
            + '<button type="submit" class="btn primary">Lọc cảnh báo</button>'
            + self.link("/ocop/expiry-alerts", "Xóa lọc")
            + '</form></div>'
        )
        rendered = []
        for row in rows:
            product_code = self.e(row.get("ma_san_pham"))
            product_href = "/ocop/products/" + quote(str(row.get("product_id")), safe="") + "?from=expiry"
            product_cell = (
                '<span class="ocop-row-id">' + product_code + '</span>'
                '<a href="' + self.e(product_href) + '"><strong>'
                + self.e(row.get("product_name")) + '</strong></a>'
            )
            entity_cell = (
                '<strong>' + self.e(row.get("entity_name")) + '</strong>'
                '<span class="ocop-contact-sub">' + self.e(row.get("ma_co_so")) + '</span>'
                '<span class="ocop-contact-sub">' + self.e(row.get("address")) + '</span>'
            )
            days = row.get("days_remaining")
            try:
                days = int(days) if days is not None else None
            except (TypeError, ValueError):
                days = None
            days_label = "Chưa xác định" if days is None else f"Còn {days} ngày"
            band_class, band_label = _expiry_band(days)
            band_html = (
                '<span class="ocop-expiry-band ' + self.e(band_class) + '">'
                + self.e(band_label) + '</span>'
            ) if band_label else ''
            expiry_label = format_ocop_date(row.get("expiry_date"))
            rendered.append(
                '<tr>'
                '<td><strong>' + self.e(days_label) + '</strong>' + band_html + '</td>'
                '<td>' + product_cell + '</td>'
                '<td>' + self.e((str(row.get("star_rank")) + " sao") if row.get("star_rank") else "—") + '</td>'
                '<td>' + self.e(expiry_label) + '</td>'
                '<td>' + entity_cell + '</td>'
                '<td>' + self.contact_markup(row) + '</td>'
                '<td><span class="ocop-contact-sub">' + self.e(row.get("administrative_unit_code")) + '</span>'
                '<strong>' + self.e(row.get("administrative_unit_name")) + '</strong></td>'
                '<td><a class="btn small" href="' + self.e(product_href) + '">Chi tiết</a></td>'
                '</tr>'
            )
        table_rows = ''.join(rendered) or '<tr><td colspan="8" class="empty">Không có sản phẩm sắp hết hạn phù hợp.</td></tr>'
        content = (
            filter_form
            + '<div class="card"><div class="ocop-detail-heading"><div><h2 class="ocop-section-heading">Sản phẩm sắp hết hạn</h2>'
            + '<p class="muted ocop-alert-note">Chỉ tính recognition hiện hành. Thông tin liên hệ được hiển thị đúng theo dữ liệu đang có.</p></div>'
            + '<span class="muted">' + self.e(len(rows)) + ' sản phẩm</span></div>'
            + '<div class="table-wrap"><table class="summary-table ocop-table ocop-expiry-table"><thead><tr>'
            + '<th>Còn hạn</th><th>Sản phẩm</th><th>Hạng</th><th>Ngày hết hạn</th><th>Chủ thể</th><th>Đầu mối liên hệ</th><th>Địa bàn</th><th>Chi tiết</th>'
            + '</tr></thead><tbody>' + table_rows + '</tbody></table></div></div>'
        )
        return self.wrap(
            "Cảnh báo hết hạn OCOP",
            "Sản phẩm có recognition hiện hành hết hạn trong vòng 3 tháng theo ngày hiện tại.",
            content,
            self.link("/ocop", "← Tra cứu OCOP"),
        )

    def overview(self):
        """Deprecated workflow dashboard retained for internal compatibility."""
        data = svc.dashboard(self.con, self.session, self.filters)
        counts = data.get("counts", data)
        cards = []
        for key, label, href in (
            ("entities", "Chủ thể OCOP", "/ocop/entities"),
            ("products", "Sản phẩm OCOP", "/ocop/products"),
            ("applications", "Hồ sơ đánh giá", "/ocop/applications"),
            ("eligible", "Hồ sơ hợp lệ", "/ocop/applications?status=eligible"),
        ):
            params = {}
            if self.filters.get("unit"):
                params["unit"] = self.filters["unit"]
            if key in ("applications", "eligible") and self.filters.get("year"):
                params["year"] = self.filters["year"]
            if params:
                href += ("&" if "?" in href else "?") + urlencode(params)
            count = format(_number(counts.get(key)), ",").replace(",", ".")
            cards.append(
                f'<a class="ocop-metric" href="{self.e(href)}"><span>{label}</span>'
                f'<strong>{count}</strong><small>Xem danh sách →</small></a>'
            )
        workflow = ""
        for key in ("draft", "submitted", "checking", "returned"):
            params = {k: self.filters[k] for k in ("unit", "year") if self.filters.get(k)}
            params["status"] = key
            href = "/ocop/applications?" + urlencode(params)
            count = format(_number(counts.get(key)), ",").replace(",", ".")
            workflow += (
                f'<a class="ocop-workflow-item" href="{self.e(href)}">'
                f'{self.badge(key)}<strong>{count}</strong></a>'
            )
        content = self.filter_bar() + '<div class="ocop-metrics">' + "".join(cards) + "</div>"
        if self.filters.get("year"):
            content += '<p class="muted">Bộ lọc năm áp dụng cho hồ sơ đánh giá. Số chủ thể và sản phẩm tính trong toàn bộ thời gian.</p>'
        content += '<section class="card"><h2 class="ocop-section-heading">Tình trạng xử lý hồ sơ</h2><div class="ocop-workflow">' + workflow + "</div></section>"
        content += (
            '<section class="card"><div class="ocop-detail-heading"><h2 class="ocop-section-heading">Bộ tiêu chí áp dụng</h2>'
            + self.link("/ocop/criteria", "Xem 26 bộ tiêu chí", "small") + '</div>'
            '<p class="muted">Danh mục sản phẩm và khung điểm được quản lý động theo Quyết định 26/2026/QĐ-TTg.</p></section>'
            '<section class="card"><h2 class="ocop-section-heading">Quy trình tiếp nhận hồ sơ</h2>'
            '<ol class="ocop-steps"><li>Tạo chủ thể</li><li>Tạo sản phẩm</li><li>Lập và gửi hồ sơ</li><li>Kiểm tra, bổ sung</li><li>Xác nhận hợp lệ</li></ol>'
            '<p class="muted">Hồ sơ hợp lệ được chuẩn bị cho bước đánh giá tiếp theo. '
            'Việc tiếp nhận hồ sơ chưa tạo kết quả công nhận sản phẩm.</p></section>'
        )
        scope_name = "tất cả đơn vị" if self.admin else next((r["name"] for r in svc.unit_options(self.con, self.session)), "đơn vị của bạn")
        return self.wrap("Tổng quan OCOP", "Theo dõi chủ thể, sản phẩm và hồ sơ của " + scope_name + ".", content, self.link("/ocop/applications/new", "Tạo hồ sơ", "primary"))

    def criteria_catalog(self):
        result = svc.list_criteria_sets(self.con, self.session, self.filters)
        rows = result.get("items", [])
        table_rows = []
        for row in rows:
            classification = self.e(row.get("product_category")) + '<div class="muted ocop-criteria-sub">' + self.e(row.get("product_group")) + '</div>'
            table_rows.append(
                '<tr><td><span class="ocop-row-id">' + self.e(row.get("code")) + '</span><strong>'
                + self.e(row.get("name")) + '</strong></td><td>' + classification + '</td><td>'
                + self.e(row.get("version")) + '</td><td>' + self.e(format_ocop_date(row.get("effective_from")))
                + '</td><td class="right"><strong>' + self.e(row.get("max_score")) + '</strong></td><td>'
                + self.link('/ocop/criteria/' + str(row["id"]), "Xem", "small") + '</td></tr>'
            )
        if not table_rows:
            table_rows.append('<tr><td colspan="6"><div class="empty">Không có bộ tiêu chí phù hợp.</div></td></tr>')
        content = (
            '<div class="notice info"><strong>Danh mục tiêu chí động.</strong> Sản phẩm được gắn với một bộ tiêu chí theo '
            'Quyết định 26/2026/QĐ-TTg. Cấu trúc được lưu trong cơ sở dữ liệu nên không cần tạo 26 biểu mẫu riêng.</div>'
            + self.filter_bar("criteria")
            + '<div class="card"><div class="table-wrap"><table class="summary-table ocop-table ocop-criteria-table"><thead><tr>'
            '<th>Bộ tiêu chí</th><th>Phân loại</th><th>Phiên bản dữ liệu</th><th>Hiệu lực từ</th><th>Điểm tối đa</th><th>Thao tác</th>'
            '</tr></thead><tbody>' + ''.join(table_rows) + '</tbody></table></div></div>'
        )
        return self.wrap(
            "Bộ tiêu chí OCOP",
            f"{result.get('total', 0)} bộ sản phẩm theo Phụ lục II Quyết định 26/2026/QĐ-TTg.",
            content,
            self.link("/ocop", "← Tổng quan"),
        )

    def criteria_detail(self, criteria_id):
        data = svc.get_criteria_tree(self.con, self.session, criteria_id)
        row = data["criteria_set"]
        criteria = data["criteria"]
        pairs = [
            ("Mã nội bộ bộ tiêu chí", row.get("code")),
            ("Tên bộ sản phẩm", row.get("name")),
            ("Nhóm sản phẩm lớn", row.get("product_category")),
            ("Nhóm", row.get("product_group")),
            ("Phân nhóm", row.get("product_subgroup")),
            ("Văn bản", row.get("legal_document")),
            ("Phiên bản dữ liệu", row.get("version")),
            ("Ngày hiệu lực", row.get("effective_from")),
            ("Điểm tối đa", row.get("max_score")),
        ]
        sections = []
        for item in criteria:
            score = "—" if item.get("max_score") is None else str(item.get("max_score")).rstrip("0").rstrip(".")
            options = item.get("options") or []
            option_html = ""
            if options:
                option_html = '<ul class="ocop-criteria-options">' + ''.join(
                    '<li><span>' + self.e(opt.get("label")) + '</span><strong>' + self.e(opt.get("score")) + ' điểm</strong></li>'
                    for opt in options
                ) + '</ul>'
            sections.append(
                '<article class="ocop-criteria-node ocop-criteria-' + self.e(item.get("item_type")) + '">'
                '<div class="ocop-criteria-node-head"><div><span class="ocop-criteria-code">' + self.e(item.get("code")) + '</span>'
                '<h3>' + self.e(item.get("title")) + '</h3></div><strong>' + self.e(score) + ' điểm</strong></div>'
                + ('<p>' + self.e(item.get("requirement_text")) + '</p>' if item.get("requirement_text") else '')
                + option_html + '</article>'
            )
        detail_note = (
            '<div class="notice info"><strong>Giai đoạn 2:</strong> hệ thống đã có 26 bộ tiêu chí và khung điểm A/B/C '
            'dạng dữ liệu động. Các tiêu chí con, lựa chọn điểm và chấm điểm thành viên Hội đồng sẽ được nạp ở giai đoạn chấm điểm tiếp theo; '
            'không phát sinh 26 form code riêng.</div>'
        )
        content = '<section class="card">' + self.details(pairs) + '</section>' + detail_note
        content += '<section class="card"><h2 class="ocop-section-heading">Cấu trúc điểm</h2><div class="ocop-criteria-tree">' + ''.join(sections) + '</div></section>'
        return self.wrap(row.get("code") + " · " + row.get("name"), "Khung bộ tiêu chí OCOP đang áp dụng.", content, self.link("/ocop/criteria", "← Danh mục bộ tiêu chí"))

    def list_page(self, kind):
        title, noun, new_label = KINDS[kind]
        result = getattr(svc, "list_" + kind)(self.con, self.session, self.filters)
        rows = [dict(r) for r in result.get("items", [])]
        if kind == "entities":
            headings = ("Mã cơ sở", "Chủ thể", "Loại cơ sở", "Xã/phường", "Trạng thái", "Thao tác")
        elif kind == "products":
            headings = ("Sản phẩm", "Chủ thể", "Bộ tiêu chí", "Nhóm sản phẩm", "Xã/phường", "Trạng thái", "Thao tác")
        else:
            headings = ("Hồ sơ / Sản phẩm", "Chủ thể", "Xã/phường", "Loại đánh giá", "Năm", "Trạng thái", "Thao tác")
        table_rows = []
        for row in rows:
            if kind == "entities":
                cells = [self.e(row.get("ma_co_so")), self.e(row.get("name")), self.e(row.get("facility_type")), self.e(row.get("unit_name"))]
            elif kind == "products":
                criteria_label = (self.e(row.get("criteria_set_code")) + '<div class="muted ocop-criteria-sub">' + self.e(row.get("criteria_set_name") or "Chưa gán") + '</div>') if row.get("criteria_set_id") else '<span class="muted">Chưa gán</span>'
                cells = [self.e(row.get("name")), self.e(row.get("entity_name")), criteria_label, self.e(row.get("product_group")), self.e(row.get("unit_name"))]
            else:
                cells = [f'<span class="ocop-row-id">#{self.e(row.get("id"))}</span>{self.e(row.get("product_name"))}', self.e(row.get("entity_name")), self.e(row.get("unit_name")), self.e(EVALUATION_LABELS.get(row.get("evaluation_type"), row.get("evaluation_type"))), self.e(row.get("year"))]
            cells.append(self.badge(row.get("status", "active")))
            cells.append(self.link(self.url(kind, row), "Xem", "small"))
            table_rows.append("<tr>" + "".join("<td>" + cell + "</td>" for cell in cells) + "</tr>")
        if not rows:
            table_rows = [f'<tr><td colspan="{len(headings)}"><div class="empty">Chưa có {noun} phù hợp. Bạn có thể đổi bộ lọc hoặc tạo {noun} mới.</div></td></tr>']
        table = '<div class="card"><div class="table-wrap"><table class="summary-table ocop-table"><thead><tr>'
        table += "".join("<th>" + text + "</th>" for text in headings) + "</tr></thead><tbody>" + "".join(table_rows) + "</tbody></table></div>"
        table += self.pagination(kind, result) + "</div>"
        content = self.filter_bar(kind) + table
        return self.wrap(title, "Tra cứu và quản lý " + noun + " trong phạm vi đơn vị được phân quyền.", content, self.link(self.url(kind, action="new"), new_label, "primary"))

    def form_page(self, kind, record=None):
        title, noun, _new_label = KINDS[kind]
        row = dict(record or {})
        editing = bool(record)
        status = row.get("status", "active")
        if editing and ((kind == "applications" and status not in ("draft", "returned")) or (kind != "applications" and status == "archived")):
            content = '<div class="notice info">Bản ghi ở trạng thái hiện tại chỉ cho phép xem thông tin.</div>'
            return self.wrap("Xem " + noun + " OCOP", "Thông tin được bảo toàn theo trạng thái xử lý.", content, self.link(self.url(kind, row), "Xem chi tiết"))
        if self.form_data is not None:
            editable = {
                "entities": ("name", "facility_type", "ma_don_vi_hanh_chinh", "address", "representative_name", "phone", "email", "tax_code", "website", "description", "updated_at"),
                "products": ("name", "ma_co_so", "criteria_set_id", "description", "updated_at"),
                "applications": ("product_id", "evaluation_type", "year", "revision"),
            }
            for field in editable[kind]:
                if field in self.form_data:
                    row[field] = self.form_data[field]
        fields = ""
        submit = "Lưu thay đổi" if editing else "Lưu " + ("bản nháp" if kind == "applications" else noun)
        blocker = ""
        if kind == "entities":
            fields += self.input("name", "Tên chủ thể / cơ sở", row.get("name", ""), required=True, attrs='maxlength="255" autocomplete="organization"')
            types = [(v, v) for v in ("Doanh nghiệp", "Hợp tác xã", "Tổ hợp tác", "Hộ gia đình", "Khác")]
            fields += self.select("facility_type", "Loại cơ sở", types, row.get("facility_type", ""), True)
            fields += self.unit_field(row.get("ma_don_vi_hanh_chinh", ""))
            fields += self.input("address", "Địa chỉ", row.get("address", ""), required=True, attrs='maxlength="255" autocomplete="street-address"')
            fields += self.input("representative_name", "Người đại diện", row.get("representative_name", ""), attrs='maxlength="255" autocomplete="name"')
            fields += self.input("phone", "Số điện thoại", row.get("phone", ""), "tel", attrs='maxlength="30" autocomplete="tel"')
            fields += self.input("email", "Email", row.get("email", ""), "email", attrs='maxlength="255" autocomplete="email"')
            fields += self.input("tax_code", "Mã số thuế", row.get("tax_code", ""), attrs='maxlength="50"')
            fields += self.input("website", "Website", row.get("website", ""), "url", attrs='maxlength="255" placeholder="https://…"')
            fields += self.textarea("description", "Thông tin giới thiệu", row.get("description", ""))
        elif kind == "products":
            entities = svc.entity_options(self.con, self.session)
            options = [(r["ma_co_so"], r.get("name", "") + " · " + r.get("unit_name", "")) for r in entities]
            if editing and row.get("ma_co_so") and not any(str(v) == str(row["ma_co_so"]) for v, _label in options):
                options.append((row["ma_co_so"], row.get("entity_name", "Chủ thể hiện tại")))
            criteria_sets = svc.criteria_set_options(self.con, self.session, active_only=True)
            criteria_options = [(r["id"], r["code"] + " · " + r["name"]) for r in criteria_sets]
            if editing and row.get("criteria_set_id") and not any(str(v) == str(row["criteria_set_id"]) for v, _label in criteria_options):
                criteria_options.append((row["criteria_set_id"], (row.get("criteria_set_code") or "Bộ tiêu chí") + " · " + (row.get("criteria_set_name") or "Bộ tiêu chí hiện tại")))
            fields += self.input("name", "Tên sản phẩm", row.get("name", ""), required=True, attrs='maxlength="255"')
            fields += self.select("ma_co_so", "Chủ thể OCOP", options, row.get("ma_co_so", ""), True)
            fields += self.select("criteria_set_id", "Bộ tiêu chí áp dụng", criteria_options, row.get("criteria_set_id", ""), True, "Chọn 1 trong 26 bộ tiêu chí…")
            fields += self.textarea("description", "Mô tả sản phẩm", row.get("description", ""))
            fields += '<p class="muted ocop-full">Xã/phường được xác định theo chủ thể. Nhóm sản phẩm được tự động lấy từ bộ tiêu chí đã chọn.</p>'
            if not options:
                blocker = '<div class="notice info">Cần có chủ thể đang sử dụng trước khi tạo sản phẩm. <a href="/ocop/entities/new">Tạo chủ thể OCOP</a>.</div>'
        else:
            products = svc.product_options(self.con, self.session)
            options = [(r["id"], r.get("name", "") + " · " + r.get("entity_name", "") + " · " + (r.get("criteria_set_code") or "chưa có tiêu chí")) for r in products]
            if editing and row.get("product_id") and not any(str(v) == str(row["product_id"]) for v, _label in options):
                options.append((row["product_id"], row.get("product_name", "Sản phẩm hiện tại")))
            fields += self.select("product_id", "Sản phẩm đăng ký đánh giá", options, row.get("product_id", ""), True)
            fields += self.select("evaluation_type", "Loại đánh giá", EVALUATION_LABELS.items(), row.get("evaluation_type", "new"), True, None)
            fields += self.input("year", "Năm đánh giá", row.get("year", date.today().year), "number", True, 'min="2000" max="2100" step="1"')
            if row.get("reviewer_note"):
                fields += '<div class="notice info ocop-full"><strong>Ý kiến kiểm tra:</strong> ' + self.e(row["reviewer_note"]) + "</div>"
            fields += '<p class="muted ocop-full">Hồ sơ được lưu để kiểm tra thông tin trước khi gửi. Chỉ hồ sơ nháp hoặc được yêu cầu bổ sung mới có thể chỉnh sửa.</p>'
            if not options:
                blocker = '<div class="notice info">Cần có sản phẩm đang sử dụng và đã gán bộ tiêu chí trước khi tạo hồ sơ. <a href="/ocop/products/new">Tạo sản phẩm OCOP</a>.</div>'
        action = self.url(kind, row, "edit") if editing else self.url(kind, action="new")
        back = self.url(kind, row) if editing else self.url(kind)
        disabled = " disabled" if blocker else ""
        error = '<div class="notice err" role="alert">' + self.e(self.error) + "</div>" if self.error else ""
        form = (
            error + blocker + f'<form class="card" action="{self.e(action)}" method="post">' + self.csrf + (self.hidden_revision(kind, row) if editing else "")
            + '<div class="ocop-form-grid">' + fields + '</div><div class="actions ocop-form-actions">'
            + f'<button class="btn primary" type="submit"{disabled}>{submit}</button>' + self.link(back, "Hủy") + "</div></form>"
        )
        return self.wrap(("Cập nhật " if editing else "Tạo ") + noun + " OCOP", "Nhập thông tin đầy đủ để quản lý và tiếp nhận hồ sơ.", form, self.link(back, "← Quay lại"))

    def details(self, pairs):
        return '<dl class="ocop-details">' + "".join(
            f'<div><dt>{self.e(label)}</dt><dd>{self.e(format_ocop_date(value))}</dd></div>'
            for label, value in pairs
        ) + "</dl>"

    def detail_page(self, kind, row):
        title, noun, _new_label = KINDS[kind]
        status = row.get("status", "active")
        if kind == "products" and self.return_context == "expiry":
            back_href, back_label = "/ocop/expiry-alerts", "← Cảnh báo hết hạn"
        else:
            back_href, back_label = "/ocop", "← Tra cứu OCOP"
        actions = self.link(back_href, back_label)
        can_edit = status in ("draft", "returned") if kind == "applications" else status != "archived"
        if can_edit:
            actions += self.link(self.url(kind, row, "edit"), "Chỉnh sửa", "primary")
        if kind == "entities":
            pairs = [
                ("Mã cơ sở", row.get("ma_co_so")), ("Tên chủ thể", row.get("name")),
                ("Loại cơ sở", row.get("facility_type")), ("Xã/phường", row.get("unit_name")),
                ("Địa chỉ", row.get("address")), ("Người đại diện", row.get("representative_name")),
                ("Điện thoại", row.get("phone")), ("Email", row.get("email")),
                ("Mã số thuế", row.get("tax_code")), ("Website", row.get("website")),
            ]
        elif kind == "products":
            rank = row.get("recognition_star") or row.get("current_star")
            pairs = [
                ("Tên sản phẩm", row.get("name")), ("Mã sản phẩm", row.get("ma_san_pham")),
                ("Chủ thể", row.get("entity_name")), ("Mã cơ sở", row.get("ma_co_so")),
                ("Loại hình chủ thể", row.get("facility_type")),
                ("Địa chỉ chủ thể", row.get("address")),
                ("Người đại diện", row.get("representative_name")), ("Điện thoại", row.get("phone")),
                ("Email", row.get("email")),
                ("Xã/phường", row.get("unit_name")), ("Nhóm sản phẩm", row.get("product_group")),
                ("Hạng sao hiện tại", f"{rank} sao" if rank else ""),
                ("Ngày công nhận gần nhất", row.get("latest_recognition_date")),
                ("Số quyết định", row.get("latest_decision_number")),
                ("Cơ quan ban hành", row.get("latest_decision_authority")),
                ("Ngày hết hạn", row.get("latest_expiry_date")),
                ("Bộ tiêu chí", ((row.get("criteria_set_code") or "") + " · " + (row.get("criteria_set_name") or "")).strip(" ·") or "Chưa gán"),
                ("Nhóm phân loại", row.get("criteria_category")), ("Phiên bản tiêu chí", row.get("criteria_version")),
            ]
        else:
            pairs = [
                ("Mã hồ sơ", "#" + str(row["id"])), ("Sản phẩm", row.get("product_name")),
                ("Chủ thể", row.get("entity_name")), ("Xã/phường", row.get("unit_name")),
                ("Loại đánh giá", EVALUATION_LABELS.get(row.get("evaluation_type"), row.get("evaluation_type"))),
                ("Năm đánh giá", row.get("year")),
                ("Bộ tiêu chí", ((row.get("criteria_set_code") or "") + " · " + (row.get("criteria_set_name") or "")).strip(" ·") or "Chưa gán"),
                ("Phiên bản tiêu chí", row.get("criteria_version")),
                ("Ngày gửi", row.get("submitted_at")), ("Ngày kiểm tra", row.get("checked_at")),
            ]
        pairs.extend([("Ngày tạo", row.get("created_at")), ("Cập nhật gần nhất", row.get("updated_at"))])
        content = '<section class="card"><div class="ocop-detail-heading"><h2 class="ocop-section-heading">Thông tin ' + noun + "</h2>" + self.badge(status) + "</div>" + self.details(pairs)
        if row.get("description"):
            content += '<h3 class="section-title">Thông tin giới thiệu</h3><p class="ocop-preserve">' + self.e(row["description"]) + "</p>"
        content += "</section>"
        if kind == "applications":
            content += self.application_actions(row)
            content += self.history(row)
            heading = "Hồ sơ #" + str(row["id"])
            subtitle = row.get("product_name", "")
        else:
            if status != "archived":
                content += '<section class="card"><h2 class="ocop-section-heading">Quản lý trạng thái</h2><p class="muted">Ngừng sử dụng khi ' + noun + ' không còn tham gia. Thông tin và hồ sơ liên quan vẫn được lưu giữ.</p>'
                content += self.post_button(kind, row, "archive", "Ngừng sử dụng", "warn") + "</section>"
            heading = row.get("name", title)
            subtitle = title
        return self.wrap(heading, subtitle, content, actions)

    def application_actions(self, row):
        status = row.get("status")
        buttons = ""
        if status in ("draft", "returned"):
            buttons += self.post_button("applications", row, "submit", "Gửi lại hồ sơ" if status == "returned" else "Gửi hồ sơ", "primary")
        if self.admin and status == "submitted":
            buttons += self.post_button("applications", row, "start-review", "Bắt đầu kiểm tra", "primary")
        if self.admin and status in ("submitted", "checking"):
            buttons += self.post_button("applications", row, "eligible", "Xác nhận hợp lệ", "ok")
        if status in ("draft", "returned") or (self.admin and status in ("submitted", "checking", "eligible")):
            buttons += self.post_button("applications", row, "cancel", "Hủy hồ sơ", "warn")
        content = '<section class="card"><h2 class="ocop-section-heading">Xử lý hồ sơ</h2>'
        if row.get("reviewer_note"):
            content += '<div class="notice info"><strong>Ý kiến kiểm tra:</strong><div class="ocop-preserve">' + self.e(row["reviewer_note"]) + "</div></div>"
        if status == "eligible":
            content += '<div class="notice info">Hồ sơ đã được xác nhận hợp lệ và chờ bước đánh giá tiếp theo.</div>'
        elif status in ("submitted", "checking"):
            content += '<p class="muted">Hồ sơ đã gửi được giữ nguyên trong thời gian kiểm tra. Có thể cập nhật khi được yêu cầu bổ sung.</p>'
        elif status == "cancelled":
            content += '<p class="muted">Hồ sơ đã hủy. Thông tin và lịch sử xử lý được lưu lại để tra cứu.</p>'
        if buttons:
            content += '<div class="actions">' + buttons + "</div>"
        if self.admin and status in ("submitted", "checking"):
            content += (
                f'<form class="ocop-return-form" method="post" action="{self.e(self.url("applications", row, "return"))}">'
                + self.csrf + self.hidden_revision("applications", row)
                + self.textarea("comment", "Nội dung yêu cầu bổ sung", required=True)
                + '<button class="btn warn" type="submit">Trả hồ sơ yêu cầu bổ sung</button></form>'
            )
        return content + "</section>"

    def history(self, row):
        logs = svc.get_reviews(self.con, self.session, row["id"])
        items = []
        for raw in logs:
            log = dict(raw)
            action = log.get("action", "")
            who = log.get("user_name") or log.get("reviewer_name") or log.get("reviewer_username") or log.get("username") or ""
            items.append(
                '<li><div class="ocop-history-top"><strong>' + self.e(REVIEW_LABELS.get(action, action))
                + '</strong><time>' + self.e(format_ocop_date(log.get("created_at"))) + "</time></div>"
                + '<div class="muted">' + self.e(who) + '</div><div class="ocop-preserve">'
                + self.e(log.get("comment", "")) + "</div></li>"
            )
        body = '<ol class="ocop-history">' + "".join(items) + "</ol>" if items else '<div class="empty">Chưa có lịch sử xử lý.</div>'
        return '<section class="card"><h2 class="ocop-section-heading">Lịch sử xử lý</h2>' + body + "</section>"
