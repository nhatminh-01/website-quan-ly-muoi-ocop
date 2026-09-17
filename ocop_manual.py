"""Direct-entry form and transport adapter for the shared OCOP registry."""
from html import escape
import re
from urllib.parse import parse_qs

import ocop_registry as registry
import ocop_services as svc


RECOGNITION_FIELDS = ("star_rank", "evaluation_type", "recognition_year", "recognition_date",
                      "decision_number", "decision_authority", "expiry_date", "note")
EVALUATIONS = (("new", "Công nhận mới"), ("re_evaluation", "Đánh giá lại"), ("upgrade", "Nâng hạng"))


def form_recognitions(data):
    indices = sorted({int(match[1]) for name in data
                      if (match := re.fullmatch(r"recognition_(\d{1,2})_(?:" + "|".join(RECOGNITION_FIELDS) + ")", name))})
    if not 1 <= len(indices) <= 50:
        raise registry.RegistryError("Nhập từ 1 đến 50 lần công nhận trong một lần lưu.")
    return [{field: data.get(f"recognition_{index}_{field}", "") for field in RECOGNITION_FIELDS} for index in indices]


def payload_from_form(data):
    unit_code = registry._bounded(data.get("unit_code"), "Xã/phường", 10, True)
    entity_name = registry._bounded(data.get("entity_name"), "Tên chủ thể", 255, True)
    product_name = registry._bounded(data.get("product_name"), "Tên sản phẩm", 255, True)
    entity_identity = f"{unit_code}|{registry.key(entity_name)}"
    product_identity = entity_identity + "|" + registry.key(product_name)
    return {
        "entity": {
            "name": entity_name, "unit_code": unit_code,
            "ma_co_so": registry.stable_code("CS", entity_identity),
            "source_key": registry.source_key("entity", unit_code, entity_name),
            **{field: data.get(field, "") for field in ("business_type", "address", "representative_name", "phone", "email")},
        },
        "product": {
            "name": product_name, "group": data.get("product_group", ""),
            "description": data.get("description", ""),
            "ma_san_pham": registry.stable_code("OP", product_identity),
            "source_key": registry.source_key("product", unit_code, entity_name, product_name),
        },
        "recognitions": form_recognitions(data),
    }


def save(con, session, data, metadata=None):
    registry.require_internal(con, session)
    return registry.publish(con, session, payload_from_form(data), source="manual",
        append_product_id=data.get("append_product_id"), selected_entity_id=data.get("selected_entity_id"),
        metadata=metadata)


def esc(value):
    return escape(str(value or ""), quote=True)


def _input(data, name, label, *, required=False, maximum=255, kind="text", readonly=False, extra=""):
    return (f'<div class="field"><label for="manual-{name}">{esc(label)}{" *" if required else ""}</label>'
            f'<input id="manual-{name}" name="{name}" type="{kind}" value="{esc(data.get(name))}" '
            f'maxlength="{maximum}" {"required" if required else ""} {"readonly" if readonly else ""} {extra}></div>')


def _select(data, name, label, options, readonly=False):
    selected = str(data.get(name, ""))
    rendered = '<option value="">-- Chọn --</option>' + "".join(
        f'<option value="{esc(value)}" {"selected" if str(value) == selected else ""}>{esc(title)}</option>'
        for value, title in options)
    preserved = f'<input type="hidden" name="{name}" value="{esc(selected)}">' if readonly else ""
    return (f'<div class="field"><label for="manual-{name}">{esc(label)} *</label>'
            f'<select id="manual-{name}" name="{name}" required {"disabled" if readonly else ""}>{rendered}</select>{preserved}</div>')


def recognition_fields(index, row=None):
    data = {f"recognition_{index}_{field}": value for field, value in (row or {}).items()}
    prefix = f"recognition_{index}_"
    fields = _select(data, prefix + "star_rank", "Hạng sao", [(str(star), f"{star} sao") for star in (3, 4, 5)])
    fields += _select(data, prefix + "evaluation_type", "Loại đánh giá", EVALUATIONS)
    fields += _input(data, prefix + "recognition_year", "Năm công nhận", required=True, kind="number", extra='min="1900" max="9999" step="1"')
    fields += _input(data, prefix + "recognition_date", "Ngày công nhận", kind="date")
    fields += _input(data, prefix + "decision_number", "Số quyết định", maximum=100)
    fields += _input(data, prefix + "decision_authority", "Cơ quan ban hành")
    fields += _input(data, prefix + "expiry_date", "Ngày hết hạn", kind="date")
    fields += _input(data, prefix + "note", "Ghi chú", maximum=5000)
    return (f'<fieldset class="manual-recognition" data-recognition><legend>Lần <span data-recognition-number>{index + 1}</span></legend>'
            f'<div class="manual-grid">{fields}</div><button type="button" class="btn small" data-remove-recognition>Xóa lần này</button></fieldset>')


def page(con, session, csrf, query="", data=None, error=None):
    registry.require_internal(con, session)
    query = parse_qs(query)
    data = dict(data or {})
    product_id = (query.get("product_id") or [""])[0] if not data else data.get("append_product_id", "")
    if (query.get("saved") or [""])[0] and not data:
        product = svc.get_product(con, session, (query["saved"])[0])
        return f'''<div class="container ocop-page manual-page"><h1>NHẬP DỮ LIỆU OCOP</h1>
          <div class="notice ok" role="status">Đã lưu dữ liệu OCOP thành công.</div>
          <div class="card"><h2>{esc(product['name'])}</h2><div class="actions">
          <a class="btn primary" href="/ocop/products/{product['id']}">Xem sản phẩm</a>
          <a class="btn" href="/ocop/manual">Nhập sản phẩm khác</a></div></div></div>'''
    if product_id and not data:
        product = svc.get_product(con, session, product_id)
        entity = svc._active_entity_by_code(con, session, product["ma_co_so"])
        aliases = {"HTX":"Hợp tác xã", "DN":"Doanh nghiệp", "Hộ kinh doanh":"Hộ", "THT":"Tổ hợp tác"}
        data = {"entity_name":entity["name"], "unit_code":entity["ma_don_vi_hanh_chinh"],
                "business_type":aliases.get(entity["facility_type"], entity["facility_type"]),
                **{field:entity[field] for field in ("address", "representative_name", "phone", "email")},
                "product_name":product["name"], "product_group":product["product_group"],
                "description":product["description"], "append_product_id":str(product["id"]),
                "selected_entity_id":str(entity["id"])}
    readonly = bool(data.get("append_product_id"))
    units = svc.unit_options(con, session)
    groups = registry.group_options(con)
    notice = f'<div class="notice err" role="alert">{esc(error)}</div>' if error else ""
    if readonly:
        notice += '<div class="notice info">Bổ sung công nhận cho sản phẩm đã có. Thông tin chủ thể và sản phẩm được giữ nguyên.</div>'
    try:
        recognitions = form_recognitions(data)
    except registry.RegistryError:
        recognitions = [{}]
    entity_fields = _input(data, "entity_name", "Tên chủ thể", required=True, readonly=readonly)
    entity_fields += _select(data, "business_type", "Loại hình chủ thể", [(item, item) for item in registry.BUSINESS_TYPES], readonly)
    entity_fields += _select(data, "unit_code", "Xã/phường", [(u["code"], u["name"]) for u in units], readonly)
    for name, label, limit, kind in (("address", "Địa chỉ", 255, "text"), ("representative_name", "Người đại diện", 255, "text"),
                                     ("phone", "Điện thoại chủ thể", 50, "tel"), ("email", "Email chủ thể", 254, "email")):
        entity_fields += _input(data, name, label, maximum=limit, kind=kind, readonly=readonly)
    product_fields = _input(data, "product_name", "Tên sản phẩm", required=True, readonly=readonly)
    product_fields += _select(data, "product_group", "Nhóm sản phẩm", [(group, group) for group in groups], readonly)
    product_fields += _input(data, "description", "Mô tả", maximum=5000, readonly=readonly)
    choices = ""
    if isinstance(error, registry.DuplicateProduct):
        for product in error.products:
            choices += (f'<div class="actions"><a class="btn" href="/ocop/products/{product["id"]}">Xem sản phẩm</a>'
                        f'<button class="btn primary" name="append_product_id" value="{product["id"]}">Thêm lần công nhận</button></div>')
    if isinstance(error, registry.AmbiguousEntity):
        choices += _select(data, "selected_entity_id", "Chọn chủ thể hiện có",
                           [(row["id"], f'{row["name"]} · {row["address"] or "Chưa có địa chỉ"} · #{row["id"]}') for row in error.entities])
    hidden = "".join(f'<input type="hidden" name="{field}" value="{esc(data[field])}">'
                     for field in ("append_product_id", "selected_entity_id") if data.get(field))
    save_button = '' if isinstance(error, registry.DuplicateProduct) else '<button class="btn primary" type="submit">Lưu dữ liệu</button>'
    return f'''<div class="container ocop-page manual-page">
      <div class="page-head"><div><h1>NHẬP DỮ LIỆU OCOP</h1>
      <div class="subtitle">Nhập chủ thể, sản phẩm và các lần công nhận. Trường có dấu * là bắt buộc.</div></div></div>
      {notice}<form method="post" action="/ocop/manual" data-ocop-manual>{csrf}{hidden}
      <section class="card"><h2>1. Thông tin chủ thể</h2><div class="manual-grid">{entity_fields}</div>
      <p class="muted">Chủ thể trùng tên trong cùng địa bàn sẽ được sử dụng lại; thông tin liên hệ đã có được giữ nguyên.</p></section>
      <section class="card"><h2>2. Thông tin sản phẩm</h2><div class="manual-grid">{product_fields}</div></section>
      <section class="card"><h2>3. Lịch sử công nhận</h2>
      <p class="muted">Lần công nhận mới nhất quyết định hạng sao hiện hành. Có thể bổ sung các lần công nhận cũ.</p>
      <div data-recognition-list>{''.join(recognition_fields(index, row) for index, row in enumerate(recognitions))}</div>
      <button class="btn" type="button" data-add-recognition>+ Thêm lần công nhận</button>
      <template data-recognition-template>{recognition_fields(0)}</template></section>
      {choices}<div class="actions manual-actions"><a class="btn" href="/ocop">Hủy</a>{save_button}</div></form>
      <script src="/assets/ocop-manual.js?v=1" defer></script></div>'''
