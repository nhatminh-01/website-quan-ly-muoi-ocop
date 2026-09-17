"""Self-service personal profiles for internal Chi cuc accounts."""
from __future__ import annotations

from html import escape
import re
from datetime import datetime

from admin_units import CHI_CUC_AGENCY_NAME


class ProfileError(ValueError):
    pass


STAFF_DEPARTMENTS = (
    "Phòng Cơ điện, ngành nghề",
    "Phòng Quản lý mỗi xã một sản phẩm - OCOP",
)
PROFILE_FIELDS = ("full_name", "job_title", "department", "official_email")


def _clean(value, limit):
    text = " ".join(str(value or "").split())
    if len(text) > limit:
        raise ProfileError(f"Thông tin vượt quá {limit} ký tự.")
    return text


def validate_profile(data, *, require_name=True, role=None):
    department = _clean(data.get("department"), 255)
    profile = {
        "full_name": _clean(data.get("full_name"), 255),
        "job_title": _clean(data.get("job_title"), 255),
        "department": department,
        "official_email": _clean(data.get("official_email"), 255).lower(),
        "agency_name": CHI_CUC_AGENCY_NAME,
    }
    if require_name and not profile["full_name"]:
        raise ProfileError("Vui lòng nhập họ và tên.")
    if role == "staff" and department not in STAFF_DEPARTMENTS:
        raise ProfileError("Chuyên viên phải chọn đúng Phòng/Bộ phận trong danh sách.")
    if role == "admin" and department and department not in STAFF_DEPARTMENTS:
        raise ProfileError("Phòng/Bộ phận không hợp lệ.")
    if profile["official_email"] and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", profile["official_email"]):
        raise ProfileError("Email công vụ không đúng định dạng.")
    return profile


def _user_role(con, user_id):
    row = con.execute("SELECT role FROM app.users WHERE id=?", (user_id,)).fetchone()
    return row["role"] if row else None


def get_profile(con, user_id):
    row = con.execute(
        """SELECT user_id,full_name,job_title,department,phone,official_email,agency_name,updated_at
           FROM app.user_profiles WHERE user_id=?""",
        (user_id,),
    ).fetchone()
    if row:
        return dict(row)
    return {
        "user_id": user_id,
        "full_name": "",
        "job_title": "",
        "department": "",
        "phone": "",
        "official_email": "",
        "agency_name": CHI_CUC_AGENCY_NAME,
        "updated_at": None,
    }


def save_profile(con, user_id, data, *, require_name=True):
    role = _user_role(con, user_id)
    profile = validate_profile(data, require_name=require_name, role=role)
    current = get_profile(con, user_id)
    preserved_phone = current.get("phone", "")
    con.execute(
        """INSERT INTO app.user_profiles
           (user_id,full_name,job_title,department,phone,official_email,agency_name,updated_at)
           VALUES(?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
           ON CONFLICT(user_id) DO UPDATE SET
             full_name=excluded.full_name,
             job_title=excluded.job_title,
             department=excluded.department,
             official_email=excluded.official_email,
             agency_name=excluded.agency_name,
             updated_at=CURRENT_TIMESTAMP""",
        (
            user_id,
            profile["full_name"],
            profile["job_title"],
            profile["department"],
            preserved_phone,
            profile["official_email"],
            CHI_CUC_AGENCY_NAME,
        ),
    )
    return profile


def save_account_profile(con, user_id, data):
    """Share one profile between admin account screens and self-service profile.

    Newly provisioned internal accounts must include a name, and staff must pick
    one of the configured departments. Existing account-only edits keep profile
    fields untouched when older clients omit them.
    """
    existing = con.execute(
        "SELECT 1 FROM app.user_profiles WHERE user_id=?", (user_id,)
    ).fetchone()
    supplied = any(field in data for field in PROFILE_FIELDS)
    if existing and not supplied:
        return
    profile = get_profile(con, user_id)
    profile.update({field: data[field] for field in PROFILE_FIELDS if field in data})
    return save_profile(con, user_id, profile, require_name=(existing is None))


def _department_options(selected):
    selected = str(selected or "").strip()
    options = ['<option value="">-- Chọn phòng/bộ phận --</option>']
    for department in STAFF_DEPARTMENTS:
        options.append(
            f'<option value="{escape(department, quote=True)}"'
            f'{" selected" if selected == department else ""}>{escape(department)}</option>'
        )
    return "".join(options)


def personal_fields(profile, *, require_name=False):
    esc = lambda value: escape("" if value is None else str(value), quote=True)
    return f"""<div class="grid profile-fields-grid">
      <div class="field"><label for="profile-full-name">Họ và tên</label><input id="profile-full-name" name="full_name" maxlength="255" {'required' if require_name else ''} value="{esc(profile.get('full_name'))}" autocomplete="name"></div>
      <div class="field"><label for="profile-job-title">Chức vụ</label><input id="profile-job-title" name="job_title" maxlength="255" value="{esc(profile.get('job_title'))}" placeholder="Ví dụ: Chuyên viên"></div>
      <div class="field"><label for="profile-department">Phòng/Bộ phận</label><select id="profile-department" name="department">{_department_options(profile.get('department'))}</select></div>
      <div class="field"><label for="profile-email">Email công vụ</label><input id="profile-email" type="email" name="official_email" maxlength="255" value="{esc(profile.get('official_email'))}" autocomplete="email"></div>
    </div>"""


def profile_body(session, profile, csrf_html, role_label):
    esc = lambda value: escape("" if value is None else str(value), quote=True)
    updated = profile.get("updated_at")
    if updated:
        try:
            updated_label = datetime.fromisoformat(str(updated).replace("Z", "+00:00")).strftime("%d/%m/%Y %H:%M")
        except ValueError:
            updated_label = str(updated)
    else:
        updated_label = "Chưa cập nhật"
    return f"""
    <div class="container profile-page">
      <div class="page-head">
        <div>
          <h1>Thông tin cá nhân</h1>
          <div class="subtitle">Cập nhật thông tin công tác và email công vụ của tài khoản đang đăng nhập.</div>
        </div>
      </div>
      <div class="notice info">Vai trò, trạng thái tài khoản, tên đăng nhập và tên cơ quan do quản trị hệ thống quản lý.</div>
      <form class="card" method="post" action="/profile">
        {csrf_html}
        <h2 class="section-title">Thông tin tài khoản</h2>
        <div class="grid">
          <div class="field"><label>Tên đăng nhập</label><input value="{esc(session.get('username'))}" readonly aria-readonly="true"></div>
          <div class="field"><label>Vai trò</label><input value="{esc(role_label)}" readonly aria-readonly="true"></div>
          <div class="field"><label>Tên cơ quan</label><input value="{esc(CHI_CUC_AGENCY_NAME)}" readonly aria-readonly="true"></div>
        </div>
        <h2 class="section-title">Thông tin cá nhân</h2>
        {personal_fields(profile, require_name=True)}
        <div class="actions" style="margin-top:18px"><button class="btn primary" type="submit">Lưu thông tin cá nhân</button></div>
        <p class="muted" style="margin:14px 0 0;font-size:12px">Cập nhật gần nhất: {esc(updated_label)}</p>
      </form>
    </div>
    """


_ACCOUNT_MENU_STYLE = """
<style id="account-menu-styles">
.profile-account.account-menu{position:relative;display:block;padding:0;border-left:0;background:transparent;border-radius:0}
.account-menu-trigger{display:flex;align-items:center;gap:11px;min-width:220px;justify-content:flex-end;border:0;background:#f2f4fb;color:#1c2940;border-radius:28px;padding:5px 7px 5px 15px;box-shadow:none}
.account-menu-trigger:hover,.account-menu-trigger[aria-expanded="true"]{background:#e9edf7}
.account-menu-trigger .account-copy{text-align:right;min-width:0}.account-menu-trigger .account-name{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:220px}.account-menu-trigger .account-role{white-space:nowrap}
.account-menu-panel{position:absolute;right:0;top:calc(100% + 9px);z-index:90;width:245px;background:#fff;border:1px solid #dce2ea;border-radius:9px;box-shadow:0 10px 26px rgba(29,42,61,.16);overflow:hidden;padding:4px 0}
.account-menu-item{display:flex;align-items:center;gap:12px;min-height:46px;padding:10px 14px;color:#414b5a;font-size:14px;border-bottom:1px solid #edf0f3}
.account-menu-item:last-child{border-bottom:0}.account-menu-item:hover{background:#f5f7fb;color:#26364c}.account-menu-item .menu-symbol{width:23px;text-align:center;color:#8a919d;font-size:16px}
.account-menu-item.logout{color:#b42318}.account-menu-divider{height:5px;background:#fafbfc;border-bottom:1px solid #edf0f3}
.activity-status{display:inline-block;border-radius:16px;padding:4px 8px;font-size:12px;font-weight:700}.activity-status.ok{background:#e7f6ee;color:#168062}.activity-status.fail{background:#fff0ed;color:#b42318}
.activity-filters{display:grid;grid-template-columns:repeat(5,minmax(150px,1fr));gap:12px;align-items:end}.activity-table{min-width:1080px}.activity-pagination{display:flex;justify-content:flex-end;gap:6px;margin-top:14px;align-items:center}
@media(max-width:900px){.account-menu-trigger{min-width:0;padding:4px}.account-menu-trigger .account-copy{display:none}.account-menu-panel{right:0;width:min(245px,calc(100vw - 24px))}.activity-filters{grid-template-columns:1fr 1fr}}
@media(max-width:620px){.activity-filters{grid-template-columns:1fr}}
</style>
"""

_ACCOUNT_MENU_SCRIPT = """
<script id="account-menu-script">
(() => {
  const root = document.querySelector('[data-account-menu]');
  if (!root) return;
  const trigger = root.querySelector('[data-account-menu-trigger]');
  const panel = root.querySelector('[data-account-menu-panel]');
  if (!trigger || !panel) return;
  const close = () => { panel.hidden = true; trigger.setAttribute('aria-expanded','false'); };
  const open = () => { panel.hidden = false; trigger.setAttribute('aria-expanded','true'); };
  trigger.addEventListener('click', event => { event.stopPropagation(); panel.hidden ? open() : close(); });
  document.addEventListener('click', event => { if (!root.contains(event.target)) close(); });
  document.addEventListener('keydown', event => { if (event.key === 'Escape') { close(); trigger.focus(); } });
})();
</script>
"""


def enhance_shell(content, session, profile, icon_html):
    """Render the account chip/dropdown and personal-profile navigation."""
    if not content or not session:
        return content
    display_name = str(profile.get("full_name") or "").strip() or str(session.get("username") or "Tài khoản").strip()
    safe_name = escape(display_name, quote=True)
    initial = escape((display_name[:1] or "U").upper(), quote=True)
    role_label = {"admin": "Quản trị Chi cục", "staff": "Chuyên viên Chi cục"}.get(
        session.get("role"), str(session.get("role") or "Tài khoản")
    )
    menu_html = f'''<div class="header-account profile-account account-menu" data-account-menu>
      <button type="button" class="account-menu-trigger" data-account-menu-trigger aria-expanded="false" aria-controls="account-menu-panel" title="Tài khoản cá nhân">
        <div class="account-copy"><div class="account-name">{safe_name}</div><div class="account-role">{escape(role_label)}</div></div>
        <span class="account-avatar" aria-hidden="true">{initial}</span>
      </button>
      <div class="account-menu-panel" id="account-menu-panel" data-account-menu-panel hidden>
        <a class="account-menu-item" href="/profile"><span class="menu-symbol">●</span><span>Thông tin cá nhân</span></a>
        <a class="account-menu-item" href="/change-password"><span class="menu-symbol">⌑</span><span>Đổi mật khẩu</span></a>
        <a class="account-menu-item" href="/activity"><span class="menu-symbol">◴</span><span>Lịch sử hoạt động</span></a>
        <div class="account-menu-divider" aria-hidden="true"></div>
        <a class="account-menu-item logout" href="/logout"><span class="menu-symbol">↪</span><span>Đăng xuất</span></a>
      </div>
    </div>'''
    content, replaced = re.subn(
        r'<div class="header-account profile-account">.*?<a class="account-logout" href="/logout">Đăng xuất</a></div>',
        menu_html,
        content,
        count=1,
        flags=re.S,
    )
    if not replaced:
        content = re.sub(
            r'<div class="account-name">.*?</div>',
            lambda match: f'<div class="account-name">{safe_name}</div>',
            content,
            count=1,
            flags=re.S,
        )
        content = re.sub(
            r'(<span class="account-avatar"[^>]*>).*?(</span>)',
            lambda match: match[1] + initial + match[2],
            content,
            count=1,
            flags=re.S,
        )

    if not re.search(r'<a class="sidebar-link[^>]*href="/profile"', content):
        active = content.startswith("<!doctype html>") and "<title>Thông tin cá nhân ·" in content
        active_class = " active" if active else ""
        aria = ' aria-current="page"' if active else ""
        profile_link = (
            f'<a class="sidebar-link{active_class}" href="/profile" title="Thông tin cá nhân"{aria}>'
            f'{icon_html("users")}<span class="sidebar-label">Thông tin cá nhân</span></a>'
        )
        marker = re.search(r'<a class="sidebar-link[^>]*href="/change-password"', content)
        if marker:
            content = content[:marker.start()] + profile_link + content[marker.start():]

    if 'id="account-menu-styles"' not in content:
        content = content.replace("</head>", _ACCOUNT_MENU_STYLE + "</head>", 1)
    if 'id="account-menu-script"' not in content:
        content = content.replace("</body>", _ACCOUNT_MENU_SCRIPT + "</body>", 1)
    return content
