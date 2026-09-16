"""Self-service personal profiles for internal Chi cuc accounts."""
from __future__ import annotations

from html import escape
import re
from datetime import datetime

from admin_units import CHI_CUC_AGENCY_NAME


class ProfileError(ValueError):
    pass


PROFILE_FIELDS = ("full_name", "job_title", "department", "phone", "official_email")


def _clean(value, limit):
    text = " ".join(str(value or "").split())
    if len(text) > limit:
        raise ProfileError(f"Thông tin vượt quá {limit} ký tự.")
    return text


def validate_profile(data, *, require_name=True):
    profile = {
        "full_name": _clean(data.get("full_name"), 255),
        "job_title": _clean(data.get("job_title"), 255),
        "department": _clean(data.get("department"), 255),
        "phone": _clean(data.get("phone"), 50),
        "official_email": _clean(data.get("official_email"), 255).lower(),
        "agency_name": CHI_CUC_AGENCY_NAME,
    }
    if require_name and not profile["full_name"]:
        raise ProfileError("Vui lòng nhập họ và tên.")
    if profile["phone"] and not re.fullmatch(r"[0-9+().\-\s]{6,50}", profile["phone"]):
        raise ProfileError("Số điện thoại không đúng định dạng.")
    if profile["official_email"] and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", profile["official_email"]):
        raise ProfileError("Email công vụ không đúng định dạng.")
    return profile


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
    profile = validate_profile(data, require_name=require_name)
    con.execute(
        """INSERT INTO app.user_profiles
           (user_id,full_name,job_title,department,phone,official_email,agency_name,updated_at)
           VALUES(?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
           ON CONFLICT(user_id) DO UPDATE SET
             full_name=excluded.full_name,
             job_title=excluded.job_title,
             department=excluded.department,
             phone=excluded.phone,
             official_email=excluded.official_email,
             agency_name=excluded.agency_name,
             updated_at=CURRENT_TIMESTAMP""",
        (
            user_id,
            profile["full_name"],
            profile["job_title"],
            profile["department"],
            profile["phone"],
            profile["official_email"],
            CHI_CUC_AGENCY_NAME,
        ),
    )
    return profile


def save_account_profile(con, user_id, data):
    """Use the account transaction and preserve fields omitted by older clients."""
    if not any(field in data for field in PROFILE_FIELDS):
        return
    profile = get_profile(con, user_id)
    profile.update({field: data[field] for field in PROFILE_FIELDS if field in data})
    return save_profile(con, user_id, profile, require_name=False)


def personal_fields(profile, *, require_name=False):
    esc = lambda value: escape("" if value is None else str(value), quote=True)
    return f"""<div class="grid">
      <div class="field"><label for="profile-full-name">Họ và tên</label><input id="profile-full-name" name="full_name" maxlength="255" {'required' if require_name else ''} value="{esc(profile.get('full_name'))}" autocomplete="name"></div>
      <div class="field"><label for="profile-job-title">Chức vụ</label><input id="profile-job-title" name="job_title" maxlength="255" value="{esc(profile.get('job_title'))}" placeholder="Ví dụ: Chuyên viên"></div>
      <div class="field"><label for="profile-department">Phòng/Bộ phận</label><input id="profile-department" name="department" maxlength="255" value="{esc(profile.get('department'))}"></div>
      <div class="field"><label for="profile-phone">Số điện thoại</label><input id="profile-phone" name="phone" maxlength="50" value="{esc(profile.get('phone'))}" inputmode="tel" autocomplete="tel"></div>
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
          <div class="subtitle">Cập nhật thông tin liên hệ và thông tin công tác của tài khoản đang đăng nhập.</div>
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


def enhance_shell(content, session, profile, icon_html):
    """Add profile navigation and display the person's name in the header."""
    if not content or not session:
        return content
    display_name = str(profile.get("full_name") or "").strip() or str(session.get("username") or "Tài khoản").strip()
    safe_name = escape(display_name, quote=True)
    initial = escape((display_name[:1] or "U").upper(), quote=True)

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
    return content
