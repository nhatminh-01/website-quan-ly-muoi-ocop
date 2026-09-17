"""Runtime renderer for the v1.1 login experience."""
from __future__ import annotations

import re

from login_theme import CHI_CUC_LOGO, REMEMBER_SECONDS


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
    style = '''<style id="login-v11-style">
html,body{min-height:100%;background:#f5faf7}.login-v11-shell{min-height:100vh;display:grid;grid-template-columns:minmax(500px,1.05fr) minmax(520px,.95fr);overflow:hidden;background:#f7fbf9;color:#17372d}.login-v11-visual{position:relative;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:56px 52px;background:linear-gradient(145deg,#e6f5ec 0%,#cdebdc 44%,#8bcda7 100%);overflow:hidden}.login-v11-visual:before{content:"";position:absolute;inset:0;background:radial-gradient(circle at 12% 8%,#ffffffd9 0 7%,transparent 25%),linear-gradient(160deg,transparent 0 58%,#147a46 58.2% 70%,#08683c 70.2% 100%);opacity:.9}.login-v11-visual:after{content:"";position:absolute;left:-8%;right:-8%;bottom:15%;height:32%;background:repeating-linear-gradient(168deg,#d8efb8 0 16px,#b8dd8e 17px 31px,#90c96d 32px 47px);clip-path:polygon(0 48%,100% 0,100% 100%,0 100%);opacity:.82}.login-v11-city{position:absolute;left:7%;right:6%;bottom:27%;height:28%;opacity:.42;background:linear-gradient(to top,#0b7952 0 4px,transparent 4px),linear-gradient(90deg,transparent 0 4%,#0b7952 4% 7%,transparent 7% 10%,#0b7952 10% 13%,transparent 13% 18%,#0b7952 18% 22%,transparent 22% 29%,#0b7952 29% 33%,transparent 33% 42%,#0b7952 42% 46%,transparent 46% 56%,#0b7952 56% 60%,transparent 60% 68%,#0b7952 68% 72%,transparent 72% 82%,#0b7952 82% 87%,transparent 87% 100%);clip-path:polygon(0 73%,4% 73%,4% 52%,7% 52%,7% 73%,10% 73%,10% 39%,13% 39%,13% 73%,18% 73%,18% 56%,22% 56%,22% 73%,29% 73%,29% 48%,33% 48%,33% 73%,42% 73%,42% 36%,46% 36%,46% 73%,56% 73%,56% 18%,60% 18%,60% 73%,68% 73%,68% 43%,72% 43%,72% 73%,82% 73%,82% 29%,87% 29%,87% 73%,100% 73%,100% 100%,0 100%)}.login-v11-brand{position:relative;z-index:3;width:min(620px,100%);text-align:center;margin-top:-11vh}.login-v11-logo{width:210px;height:210px;border-radius:50%;object-fit:cover;display:block;margin:0 auto 22px;background:white;box-shadow:0 18px 45px #0b5f3926}.login-v11-brand h2{margin:0;color:#08713f;font-size:34px;line-height:1.12;letter-spacing:-.6px;font-weight:850;text-transform:uppercase}.login-v11-brand h3{margin:8px 0 0;color:#13804a;font-size:27px;line-height:1.2;font-weight:500;text-transform:uppercase}.login-v11-network{position:absolute;left:9%;bottom:10%;z-index:3;display:flex;gap:16px}.login-v11-chip{width:74px;height:74px;border:1px solid #ffffffba;border-radius:18px;display:grid;place-items:center;color:white;background:#08713f45;backdrop-filter:blur(4px);font-size:30px}.login-v11-panel{position:relative;min-height:100vh;display:flex;flex-direction:column;justify-content:center;padding:84px clamp(38px,7vw,120px) 46px;background:radial-gradient(circle at 92% 8%,#d9f5e8 0,transparent 25%),linear-gradient(155deg,#f9fdfb 0%,#eef8f3 100%)}.login-v11-maker{position:absolute;top:30px;right:clamp(28px,5vw,78px);display:flex;align-items:center;gap:14px;color:#18764a;text-align:right}.login-v11-maker-icon{width:39px;height:39px;border:2px solid #1a8a54;border-radius:50%;display:grid;place-items:center;font-size:21px}.login-v11-maker small{display:block;color:#668b79;font-size:11px;letter-spacing:.4px}.login-v11-maker strong{display:block;font-size:12px;line-height:1.35;text-transform:uppercase;max-width:340px}.login-v11-card{width:min(610px,100%);margin:auto;background:#ffffffef;border:1px solid #dbe9e1;border-radius:24px;padding:48px 48px 38px;box-shadow:0 24px 70px rgba(20,93,58,.09)}.login-v11-accent{width:82px;height:5px;border-radius:8px;background:#139052;margin-bottom:27px}.login-v11-card h1{margin:0;color:#075d39;font-size:36px;line-height:1.15;letter-spacing:-.8px}.login-v11-subtitle{margin:10px 0 29px;color:#637486;font-size:17px;line-height:1.55}.login-v11-card .field{margin:17px 0}.login-v11-card .field label{font-size:15px;color:#33445a;font-weight:750}.login-v11-card .field input{min-height:58px;border-radius:10px;font-size:16px;padding:14px 16px;border-color:#ccd9e2}.login-v11-card .field input:focus{border-color:#159456;box-shadow:0 0 0 3px #1594561c;outline:none}.login-v11-options{display:flex;align-items:center;justify-content:space-between;gap:16px;margin:14px 0 22px}.login-v11-remember{display:inline-flex;align-items:center;gap:10px;color:#46586b;font-size:14px;cursor:pointer;user-select:none}.login-v11-remember input{width:19px;height:19px;accent-color:#11894f}.login-v11-submit{width:100%;min-height:58px;border:0;border-radius:10px;background:linear-gradient(90deg,#10894e,#159b59);color:white;font-size:16px;font-weight:800;box-shadow:0 8px 22px #11894f2b}.login-v11-submit:hover{filter:brightness(.96)}.login-v11-info{margin-top:20px;border:1px solid #cfe5d9;border-radius:11px;background:#f0faf5;padding:15px 17px;color:#537064;font-size:13px;line-height:1.6}.login-v11-info b{display:block;color:#116f45;margin-bottom:2px}.login-v11-error{margin:0 0 14px;border:1px solid #efc8bf;border-radius:9px;background:#fff0ed;color:#a43120;padding:11px 13px;font-size:13px}.login-v11-foot{margin:20px auto 0;color:#6b8c7c;font-size:12px;text-align:center;font-style:italic}.login-v11-visual-note{position:absolute;z-index:4;left:48px;bottom:34px;color:#ecfff4;font-size:12px;letter-spacing:1.1px;text-transform:uppercase}.login-v11-visual-note span{display:inline-block;margin-right:18px}.login-v11-card input:-webkit-autofill{-webkit-box-shadow:0 0 0 1000px white inset;-webkit-text-fill-color:#26364c}
@media(max-width:1050px){.login-v11-shell{grid-template-columns:42% 58%}.login-v11-visual{padding:40px 26px}.login-v11-logo{width:150px;height:150px}.login-v11-brand h2{font-size:25px}.login-v11-brand h3{font-size:21px}.login-v11-panel{padding-left:40px;padding-right:40px}.login-v11-card{padding:38px 34px}}
@media(max-width:760px){.login-v11-shell{display:block;min-height:100vh}.login-v11-visual{min-height:230px;height:230px;padding:24px}.login-v11-brand{margin:0}.login-v11-logo{width:90px;height:90px;margin-bottom:10px}.login-v11-brand h2{font-size:18px}.login-v11-brand h3{font-size:15px}.login-v11-city,.login-v11-network,.login-v11-visual-note{display:none}.login-v11-panel{min-height:calc(100vh - 230px);padding:76px 18px 28px}.login-v11-maker{top:20px;left:20px;right:20px;justify-content:center;text-align:left}.login-v11-maker strong{font-size:10px}.login-v11-card{padding:30px 22px;border-radius:18px}.login-v11-card h1{font-size:29px}.login-v11-subtitle{font-size:14px}.login-v11-card .field input{min-height:52px}.login-v11-foot{font-size:11px}}
</style>'''

    page = f'''{style}<div class="login-v11-shell">
      <section class="login-v11-visual" aria-label="Nhận diện Chi cục Phát triển nông thôn">
        <div class="login-v11-city" aria-hidden="true"></div>
        <div class="login-v11-brand"><img class="login-v11-logo" src="{CHI_CUC_LOGO}" alt="Biểu trưng Chi cục Phát triển nông thôn Thành phố Hồ Chí Minh"><h2>Chi cục Phát triển nông thôn</h2><h3>Thành phố Hồ Chí Minh</h3></div>
        <div class="login-v11-network" aria-hidden="true"><span class="login-v11-chip">🌱</span><span class="login-v11-chip">⚙</span><span class="login-v11-chip">◫</span></div>
        <div class="login-v11-visual-note"><span>Nông nghiệp bền vững</span><span>Nông thôn hiện đại</span><span>Vì cộng đồng phát triển</span></div>
      </section>
      <section class="login-v11-panel">
        <div class="login-v11-maker"><span class="login-v11-maker-icon">⌁</span><div><small>Đơn vị tạo lập hệ thống</small><strong>Trung tâm Chuyển đổi số Nông nghiệp và Môi trường</strong></div></div>
        <div class="login-v11-card"><div class="login-v11-accent"></div><h1>Đăng nhập hệ thống</h1><div class="login-v11-subtitle">Hệ thống quản lý nghiệp vụ nội bộ<br>Chi cục Phát triển nông thôn Thành phố Hồ Chí Minh</div>{error}
          <form method="post" action="/login" id="login-v11-form">
            <div class="field"><label for="login-v11-user">Tên đăng nhập</label><input id="login-v11-user" name="username" autocomplete="username" placeholder="Nhập tên đăng nhập" required autofocus></div>
            <div class="field"><label for="login-v11-password">Mật khẩu</label><input id="login-v11-password" type="password" name="password" autocomplete="current-password" placeholder="Nhập mật khẩu" required></div>
            <div class="login-v11-options"><label class="login-v11-remember"><input id="login-v11-remember" type="checkbox" name="remember" value="1">Ghi nhớ đăng nhập</label><span class="muted">Thiết bị tin cậy</span></div>
            <button class="login-v11-submit" type="submit">Đăng nhập →</button>
          </form>
          <div class="login-v11-info"><b>Tài khoản nội bộ Chi cục.</b>Liên hệ quản trị để được cấp tài khoản. Hệ thống không còn cấp tài khoản đăng nhập cho xã/phường.</div>
        </div>
        <div class="login-v11-foot">Chuyển đổi số vì nền nông nghiệp phát triển bền vững</div>
      </section>
    </div>
    <script>(function(){{var f=document.getElementById('login-v11-form'),u=document.getElementById('login-v11-user'),r=document.getElementById('login-v11-remember');if(!f||!u||!r)return;try{{var saved=localStorage.getItem('salt-login-username');if(saved){{u.value=saved;r.checked=true;}}}}catch(e){{}}f.addEventListener('submit',function(){{try{{if(r.checked){{localStorage.setItem('salt-login-username',u.value.trim());document.cookie='remember_login=1; Path=/; Max-Age={REMEMBER_SECONDS}; SameSite=Lax';}}else{{localStorage.removeItem('salt-login-username');document.cookie='remember_login=; Path=/; Max-Age=0; SameSite=Lax';}}}}catch(e){{}}}});}})();</script>'''
    return content[:start] + page + content[end:]
