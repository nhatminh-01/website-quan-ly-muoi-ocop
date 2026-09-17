(() => {
  const header = document.querySelector('.site-header');
  const menu = document.getElementById('sidebar-toggle');
  const sidebar = document.getElementById('site-sidebar');
  const main = document.getElementById('main-content');
  const backdrop = document.getElementById('sidebar-backdrop');
  const mobile = window.matchMedia('(max-width: 900px)');
  const sidebarScrollKey = 'salt-sidebar-scroll';
  let collapsed = false;
  try { collapsed = localStorage.getItem('salt-sidebar-collapsed') === 'true'; } catch (_) {}
  function syncMenu() {
    if (!menu || !sidebar) return;
    const opened = mobile.matches ? document.body.classList.contains('sidebar-open') : !collapsed;
    menu.setAttribute('aria-expanded', String(opened));
    menu.setAttribute('aria-label', opened ? 'Thu gọn menu' : 'Mở menu');
    menu.title = opened ? 'Thu gọn menu' : 'Mở menu';
    sidebar.inert = mobile.matches && !opened;
    if (main) main.inert = mobile.matches && opened;
    document.body.classList.toggle('sidebar-collapsed', !mobile.matches && collapsed);
  }
  function closeDrawer() {
    const focusInDrawer = sidebar?.contains(document.activeElement);
    document.body.classList.remove('sidebar-open');
    syncMenu();
    if (focusInDrawer && mobile.matches) menu?.focus();
  }
  if (menu) menu.addEventListener('click', () => {
    if (mobile.matches) document.body.classList.toggle('sidebar-open');
    else {
      collapsed = !collapsed;
      try { localStorage.setItem('salt-sidebar-collapsed', String(collapsed)); } catch (_) {}
    }
    syncMenu();
    if (mobile.matches && document.body.classList.contains('sidebar-open')) {
      sidebar?.querySelector('input, a, button')?.focus({ preventScroll: true });
    }
  });
  if (backdrop) backdrop.addEventListener('click', () => { closeDrawer(); menu?.focus(); });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && document.body.classList.contains('sidebar-open')) {
      closeDrawer(); menu?.focus();
    }
  });
  mobile.addEventListener('change', closeDrawer);
  if (header) {
    const resizeHeader = () => document.documentElement.style.setProperty('--header-height', `${header.offsetHeight}px`);
    resizeHeader();
    new ResizeObserver(resizeHeader).observe(header);
  }
  document.querySelectorAll('.sidebar-group').forEach(group => {
    const key = 'salt-sidebar-group-' + group.dataset.group;
    try { group.open = group.dataset.active === 'true' || localStorage.getItem(key) === 'true'; } catch (_) {}
    group.addEventListener('toggle', () => {
      try { localStorage.setItem(key, String(group.open)); } catch (_) {}
    });
  });
  syncMenu();

  function restoreSidebarScroll() {
    if (!sidebar) return;
    let savedScrollTop;
    try {
      const savedValue = sessionStorage.getItem(sidebarScrollKey);
      if (savedValue === null) return;
      savedScrollTop = Number(savedValue);
    } catch (_) { return; }
    if (!Number.isFinite(savedScrollTop)) return;

    sidebar.scrollTop = Math.max(0, Math.min(savedScrollTop, sidebar.scrollHeight - sidebar.clientHeight));
    const activeLink = sidebar.querySelector('.sidebar-link.active');
    if (!activeLink) return;
    const sidebarRect = sidebar.getBoundingClientRect();
    const activeRect = activeLink.getBoundingClientRect();
    const activeIsVisible = activeRect.bottom > sidebarRect.top && activeRect.top < sidebarRect.bottom;
    if (!activeIsVisible) activeLink.scrollIntoView({ block: 'nearest' });
  }

  if (sidebar) {
    sidebar.addEventListener('scroll', () => {
      try { sessionStorage.setItem(sidebarScrollKey, String(sidebar.scrollTop)); } catch (_) {}
    }, { passive: true });
    requestAnimationFrame(() => requestAnimationFrame(restoreSidebarScroll));
  }

  // Weekly summary details stay in a modal so the table width does not change.
  const weeklyDialogTriggers = document.querySelectorAll('[data-weekly-dialog]');
  weeklyDialogTriggers.forEach(trigger => {
    const dialog = document.getElementById(trigger.dataset.weeklyDialog);
    if (!dialog) return;
    trigger.addEventListener('click', () => {
      dialog._weeklyLastTrigger = trigger;
      if (typeof dialog.showModal === 'function') dialog.showModal();
      else dialog.setAttribute('open', '');
    });
  });
  document.querySelectorAll('[data-weekly-dialog-close]').forEach(closeButton => {
    closeButton.addEventListener('click', () => {
      const dialog = closeButton.closest('.weekly-dialog');
      if (!dialog) return;
      if (typeof dialog.close === 'function') dialog.close();
      else dialog.removeAttribute('open');
      dialog._weeklyLastTrigger?.focus();
    });
  });
  document.querySelectorAll('.weekly-dialog').forEach(dialog => {
    dialog.addEventListener('click', event => {
      if (event.target !== dialog) return;
      if (typeof dialog.close === 'function') dialog.close();
      else dialog.removeAttribute('open');
      dialog._weeklyLastTrigger?.focus();
    });
  });

  // Active deployment is Chi cục-only. Locality remains a data dimension for imports and filters.
  const login = document.querySelector('.login');
  if (login) {
    const intro = login.querySelector('p');
    if (intro) intro.textContent = 'Hệ thống nghiệp vụ nội bộ Chi cục Phát triển nông thôn Thành phố Hồ Chí Minh.';
    const info = login.querySelector('.notice.info');
    if (info) info.innerHTML = '<b>Tài khoản nội bộ Chi cục.</b><br>Liên hệ quản trị để được cấp tài khoản. Hệ thống không còn cấp tài khoản đăng nhập cho xã/phường.';
  }
  const sidebarFooter = document.querySelector('.sidebar-footer p');
  if (sidebarFooter) sidebarFooter.textContent = 'Quản lý tập trung dữ liệu Diêm nghiệp và OCOP.';

  const usersHeading = [...document.querySelectorAll('.page-head h1')].find(el => el.textContent.trim() === 'Tài khoản đơn vị');
  if (usersHeading) {
    usersHeading.textContent = 'Tài khoản Chi cục';
    const subtitle = usersHeading.parentElement?.querySelector('.subtitle');
    if (subtitle) subtitle.textContent = 'Quản lý tài khoản quản trị và chuyên viên nội bộ Chi cục.';
    document.querySelector('a[href="/ocop/access"]')?.remove();
    const createCard = document.querySelector('form[action="/users/new"]')?.closest('.card');
    if (createCard && !document.querySelector('.chi-cuc-only-note')) {
      const note = document.createElement('div');
      note.className = 'notice info chi-cuc-only-note';
      note.textContent = 'Chỉ tạo tài khoản Quản trị Chi cục hoặc Chuyên viên Chi cục. Tài khoản xã/phường cũ chỉ được giữ để bảo toàn lịch sử dữ liệu.';
      createCard.parentNode.insertBefore(note, createCard);
    }
    document.querySelectorAll('.summary-table tbody tr').forEach(row => {
      const cells = row.querySelectorAll('td');
      if (cells.length < 5 || cells[1].textContent.trim() !== 'Đơn vị xã/phường') return;
      row.classList.add('legacy-unit-account');
      cells[1].textContent = 'Tài khoản xã/phường (cũ)';
      row.querySelector('a[href$="/edit"]')?.remove();
      const status = cells[3].textContent.trim();
      cells[4].querySelectorAll('form').forEach(form => {
        if (!form.action.endsWith('/deactivate')) form.remove();
      });
      if (status !== 'Hoạt động') cells[4].textContent = 'Đã ngưng · chỉ lưu lịch sử';
    });
  }

  const clock = document.getElementById('clock-time');
  const calendar = document.getElementById('clock-date');
  if (clock && calendar) {
    const updateClock = () => {
      const now = new Date();
      const options = { timeZone: 'Asia/Ho_Chi_Minh' };
      clock.textContent = now.toLocaleTimeString('vi-VN', { ...options, hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
      calendar.textContent = now.toLocaleDateString('vi-VN', { ...options, weekday: 'long', day: '2-digit', month: '2-digit', year: 'numeric' });
      clock.dateTime = now.toISOString();
    };
    updateClock();
    setInterval(updateClock, 1000);
  }
  document.querySelectorAll('.js-loading-form').forEach(form => {
    form.addEventListener('submit', () => {
      const button = form.querySelector('button[type="submit"]');
      if (!button) return;
      button.disabled = true;
      button.setAttribute('aria-busy', 'true');
      button.textContent = button.dataset.loadingText || 'Đang xử lý...';
    });
  });
  document.querySelectorAll('form select[name="role"]').forEach(role => {
    const form = role.closest('form');
    const legacyUnitEdit = /^\/users\/\d+\/edit\/?$/.test(location.pathname) && role.value === 'unit';
    if (legacyUnitEdit) {
      const notice = document.createElement('div');
      notice.className = 'notice info';
      notice.textContent = 'Đây là tài khoản xã/phường cũ. Hệ thống giữ lại để bảo toàn lịch sử; hãy ngưng kích hoạt từ danh sách tài khoản nếu không còn sử dụng.';
      form.prepend(notice);
      form.querySelector('button[type="submit"]')?.setAttribute('disabled', 'disabled');
    } else {
      role.querySelector('option[value="unit"]')?.remove();
      if (!['admin', 'staff'].includes(role.value)) role.value = 'staff';
    }
    const syncUnitFields = () => {
      const isUnit = role.value === 'unit';
      for (const [selector, visible] of [['[data-unit-field]', isUnit], ['[data-office-field]', !isUnit]]) {
        const field = form.querySelector(selector);
        if (!field) continue;
        field.hidden = !visible;
        field.querySelectorAll('input, select').forEach(input => {
          input.disabled = !visible;
          input.required = visible;
        });
      }
    };
    role.addEventListener('change', syncUnitFields);
    syncUnitFields();
  });
})();
