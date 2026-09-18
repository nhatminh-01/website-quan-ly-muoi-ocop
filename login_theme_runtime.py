"""Runtime renderer for the v1.1 login experience."""
from __future__ import annotations

import re

from login_theme import REMEMBER_SECONDS


def remember_cookie_enabled(raw_cookie: str) -> bool:
    return "remember_login=1" in str(raw_cookie or "")


def extend_session_cookie(value: str, remember: bool) -> str:
    if not remember or not str(value).startswith("salt_session=") or "Max-Age=" in value:
        return value
    return f"{value}; Max-Age={REMEMBER_SECONDS}"


def _error_notice(markup: str) -> str:
    match = re.search(r'<div class="notice err">(.*?)</div>', markup, flags=re.S)
    if not match:
        return ""
    return f'<div class="login-v11-error" role="alert">{match.group(1)}</div>'


def enhance_login_page(content: str) -> str:
    start = content.find('<div class="login-wrap">')
    if start < 0:
        return content
    marker = '<div class="notice info"'
    info_at = content.find(marker, start)
    if info_at < 0:
        return content
    end = content.find('</div></div>', info_at)
    if end < 0:
        return content
    end += len('</div></div>')
    if content[end:end + 6] == '</div>':
        end += 6

    error = _error_notice(content[start:end])
    style = '<link rel="stylesheet" href="/assets/login.css?v=20260918-compact">'
    page = f'''{style}<main class="login-v11-shell">
      <section class="login-v11-visual" aria-label="Nhận diện Chi cục Phát triển nông thôn">
        <img class="login-v11-hero" src="/assets/login-hero.png" width="1198" height="1313" fetchpriority="high" alt="Chi cục Phát triển nông thôn Thành phố Hồ Chí Minh — cảnh nông nghiệp, thành phố và chuyển đổi số">
      </section>
      <section class="login-v11-panel" aria-labelledby="login-v11-heading">
        <div class="login-v11-topline" aria-hidden="true"><span>Hành chính số</span><i>·</i><span>Nông nghiệp thông minh</span><i>·</i><span>Phục vụ người dân</span></div>
        <div class="login-v11-card">
          <div class="login-v11-accent" aria-hidden="true"></div>
          <h1 id="login-v11-heading">Đăng nhập hệ thống</h1>
          <div class="login-v11-subtitle">Hệ thống quản lý nghiệp vụ nội bộ<span>Chi cục Phát triển nông thôn Thành phố Hồ Chí Minh</span></div>{error}
          <form method="post" action="/login" id="login-v11-form">
            <div class="field"><label for="login-v11-user">Tên đăng nhập</label><div class="login-v11-input">
              <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="7" r="4"/><path d="M4 22v-3a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v3"/></svg>
              <input id="login-v11-user" name="username" autocomplete="username" placeholder="Nhập tên đăng nhập" required autofocus>
            </div></div>
            <div class="field"><label for="login-v11-password">Mật khẩu</label><div class="login-v11-input">
              <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="10" width="16" height="12" rx="2"/><path d="M7 10V6a5 5 0 0 1 10 0v4m-5 5v3"/><circle cx="12" cy="15" r="1"/></svg>
              <input id="login-v11-password" type="password" name="password" autocomplete="current-password" placeholder="Nhập mật khẩu" required>
            </div></div>
            <div class="login-v11-options"><label class="login-v11-remember"><input id="login-v11-remember" type="checkbox" name="remember" value="1">Ghi nhớ đăng nhập</label><span>Thiết bị tin cậy</span></div>
            <button class="login-v11-submit" type="submit"><span>Đăng nhập</span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 12h18m-8-8 8 8-8 8"/></svg></button>
          </form>
          <div class="login-v11-info"><svg viewBox="0 0 28 28" aria-hidden="true"><circle cx="14" cy="14" r="12"/><path d="M14 12v8m-2 0h4"/><circle cx="14" cy="7.5" r=".8"/></svg><div><b>Tài khoản nội bộ Chi cục.</b>Liên hệ quản trị để được cấp tài khoản. Hệ thống không còn cấp tài khoản đăng nhập cho xã/phường.</div></div>
        </div>
        <footer class="login-v11-footer">
          <div class="login-v11-maker"><svg viewBox="0 0 32 42" aria-hidden="true"><path d="M16 39V14m0 13C4 29 2 20 3 15c8 0 13 5 13 12Zm0 5c12 1 14-7 13-12-8 0-13 5-13 12ZM16 3c-11 8-9 14 0 18 9-4 11-10 0-18Zm-8 18 5 4m11 1-5 4"/></svg><div><small>Đơn vị tạo lập hệ thống</small><strong>Trung tâm Chuyển đổi số Nông nghiệp và Môi trường</strong></div></div>
          <div class="login-v11-foot">Vì nông thôn thịnh vượng<br><span>Vì người dân hạnh phúc</span></div>
        </footer>
      </section>
    </main>
    <script>(function(){{var f=document.getElementById('login-v11-form'),u=document.getElementById('login-v11-user'),r=document.getElementById('login-v11-remember');if(!f||!u||!r)return;try{{var saved=localStorage.getItem('salt-login-username');if(saved){{u.value=saved;r.checked=true;}}}}catch(e){{}}f.addEventListener('submit',function(){{try{{if(r.checked){{localStorage.setItem('salt-login-username',u.value.trim());document.cookie='remember_login=1; Path=/; Max-Age={REMEMBER_SECONDS}; SameSite=Lax';}}else{{localStorage.removeItem('salt-login-username');document.cookie='remember_login=; Path=/; Max-Age=0; SameSite=Lax';}}}}catch(e){{}}}});}})();</script>'''
    return content[:start] + page + content[end:]
