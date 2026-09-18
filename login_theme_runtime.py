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
    style = '''<link rel="stylesheet" href="/assets/login.css?v=20260918-password-toggle">
<style id="login-contact-style">
.login-v11-contact{position:absolute;z-index:2;left:0;right:0;bottom:0;min-height:17.5%;padding:18px clamp(28px,4vw,68px) 20px;display:flex;flex-direction:column;justify-content:center;color:#fff;background:linear-gradient(180deg,rgba(5,105,52,.96),rgba(4,91,45,.99));box-shadow:0 -1px 0 rgba(255,255,255,.12)}
.login-v11-contact::before{content:"";position:absolute;left:0;right:0;top:-24px;height:25px;background:linear-gradient(165deg,transparent 0 48%,rgba(7,111,55,.96) 49% 100%);pointer-events:none}
.login-v11-contact-title{position:relative;margin:0 0 9px;font-size:clamp(13px,1.05vw,18px);line-height:1.25;font-weight:800;letter-spacing:.15px;text-transform:uppercase}
.login-v11-contact-list{position:relative;display:grid;grid-template-columns:1fr;gap:5px;margin:0;padding:0;list-style:none}
.login-v11-contact-item{display:flex;align-items:center;gap:10px;min-width:0;font-size:clamp(11px,.82vw,14px);line-height:1.35;color:#f8fffb}
.login-v11-contact-item svg{flex:0 0 18px;width:18px;height:18px;fill:none;stroke:#d8f6df;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
.login-v11-contact-item span,.login-v11-contact-item a{min-width:0;color:inherit;text-decoration:none;overflow-wrap:anywhere}
.login-v11-contact-item a:hover{text-decoration:underline}
@media(max-width:1100px) and (min-width:761px){.login-v11-contact{min-height:18%;padding:15px 28px 17px}.login-v11-contact-title{font-size:13px}.login-v11-contact-item{font-size:11px;gap:8px}.login-v11-contact-item svg{width:16px;height:16px;flex-basis:16px}}
@media(max-width:760px){.login-v11-contact{min-height:112px;padding:12px 16px 13px;background:linear-gradient(180deg,rgba(5,105,52,.97),rgba(4,91,45,.995))}.login-v11-contact::before{top:-13px;height:14px}.login-v11-contact-title{margin-bottom:7px;font-size:11px}.login-v11-contact-list{grid-template-columns:1fr 1fr;gap:5px 12px}.login-v11-contact-item{font-size:9px;gap:6px}.login-v11-contact-item:first-child{grid-column:1/-1}.login-v11-contact-item svg{width:13px;height:13px;flex-basis:13px}}
@media(max-width:430px){.login-v11-contact{min-height:118px}.login-v11-contact-list{grid-template-columns:1fr}.login-v11-contact-item:first-child{grid-column:auto}.login-v11-contact-item:nth-child(4),.login-v11-contact-item:nth-child(5){display:none}}
</style>'''
    page = f'''{style}<main class="login-v11-shell">
      <section class="login-v11-visual" aria-label="Nhận diện Chi cục Phát triển nông thôn">
        <img class="login-v11-hero" src="/assets/login-hero.png" width="1198" height="1313" fetchpriority="high" alt="Chi cục Phát triển nông thôn Thành phố Hồ Chí Minh — cảnh nông nghiệp, thành phố và chuyển đổi số">
        <div class="login-v11-contact" aria-label="Thông tin liên hệ Chi cục Phát triển nông thôn Thành phố Hồ Chí Minh">
          <div class="login-v11-contact-title">Chi cục Phát triển nông thôn TP. Hồ Chí Minh</div>
          <ul class="login-v11-contact-list">
            <li class="login-v11-contact-item"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m3 11 9-8 9 8"/><path d="M5 10v10h14V10M9 20v-6h6v6"/></svg><span>176 Hai Bà Trưng, Phường Tân Định, TP. Hồ Chí Minh</span></li>
            <li class="login-v11-contact-item"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6.5 3h3l1.5 5-2 1.5a15 15 0 0 0 5.5 5.5L16 13l5 1.5v3A3.5 3.5 0 0 1 17.5 21C9.5 21 3 14.5 3 6.5A3.5 3.5 0 0 1 6.5 3Z"/></svg><a href="tel:02838226793">028 3822 6793</a></li>
            <li class="login-v11-contact-item"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m4 7 8 6 8-6"/></svg><a href="mailto:ccptnt.snnmt@tphcm.gov.vn">ccptnt.snnmt@tphcm.gov.vn</a></li>
            <li class="login-v11-contact-item"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18"/></svg><a href="http://ccptnt.vn" target="_blank" rel="noopener noreferrer">http://ccptnt.vn</a></li>
          </ul>
        </div>
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
              <button class="login-v11-password-toggle" type="button" aria-label="Hiển thị mật khẩu" aria-pressed="false" title="Hiển thị mật khẩu">
                <svg class="password-eye-open" viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></svg>
                <svg class="password-eye-closed" viewBox="0 0 24 24" aria-hidden="true"><path d="m3 3 18 18M10.6 10.6a2 2 0 0 0 2.8 2.8M9.9 5.2A11.5 11.5 0 0 1 12 5c6.5 0 10 7 10 7a16 16 0 0 1-2.2 3.1M6.6 6.6C3.7 8.4 2 12 2 12s3.5 7 10 7a10.7 10.7 0 0 0 4-.8"/></svg>
              </button>
            </div></div>
            <div class="login-v11-options"><label class="login-v11-remember"><input id="login-v11-remember" type="checkbox" name="remember" value="1">Ghi nhớ đăng nhập</label><span>Thiết bị tin cậy</span></div>
            <button class="login-v11-submit" type="submit"><span>Đăng nhập</span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 12h18m-8-8 8 8-8 8"/></svg></button>
          </form>
          <div class="login-v11-info"><svg viewBox="0 0 28 28" aria-hidden="true"><circle cx="14" cy="14" r="12"/><path d="M14 12v8m-2 0h4"/><circle cx="14" cy="7.5" r=".8"/></svg><div><b>Tài khoản nội bộ Chi cục.</b>Liên hệ quản trị để được cấp tài khoản.</div></div>
        </div>
        <footer class="login-v11-footer">
          <div class="login-v11-maker"><svg viewBox="0 0 32 42" aria-hidden="true"><path d="M16 39V14m0 13C4 29 2 20 3 15c8 0 13 5 13 12Zm0 5c12 1 14-7 13-12-8 0-13 5-13 12ZM16 3c-11 8-9 14 0 18 9-4 11-10 0-18Zm-8 18 5 4m11 1-5 4"/></svg><div><small>Đơn vị tạo lập và vận hành</small><strong>Trung tâm Chuyển đổi số Nông nghiệp và Môi trường</strong></div></div>
          <div class="login-v11-foot">Vì nông thôn thịnh vượng<br><span>Vì người dân hạnh phúc</span></div>
        </footer>
      </section>
    </main>
    <script>(function(){{var f=document.getElementById('login-v11-form'),u=document.getElementById('login-v11-user'),r=document.getElementById('login-v11-remember'),p=document.getElementById('login-v11-password'),t=document.querySelector('.login-v11-password-toggle');if(!f||!u||!r)return;if(p&&t){{t.addEventListener('click',function(){{var showing=p.type==='text';p.type=showing?'password':'text';t.setAttribute('aria-pressed',showing?'false':'true');t.setAttribute('aria-label',showing?'Hiển thị mật khẩu':'Ẩn mật khẩu');t.setAttribute('title',showing?'Hiển thị mật khẩu':'Ẩn mật khẩu');}});}}try{{var saved=localStorage.getItem('salt-login-username');if(saved){{u.value=saved;r.checked=true;}}}}catch(e){{}}f.addEventListener('submit',function(){{try{{if(r.checked){{localStorage.setItem('salt-login-username',u.value.trim());document.cookie='remember_login=1; Path=/; Max-Age={REMEMBER_SECONDS}; SameSite=Lax';}}else{{localStorage.removeItem('salt-login-username');document.cookie='remember_login=; Path=/; Max-Age=0; SameSite=Lax';}}}}catch(e){{}}}});}})();</script>'''
    return content[:start] + page + content[end:]
