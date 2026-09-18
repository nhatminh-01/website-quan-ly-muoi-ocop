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
  if (sidebarFooter) sidebarFooter.textContent = 'v.1.0';

  // OCOP has one "Nhập dữ liệu" menu item and it opens direct-entry immediately.
  // Excel import remains available from the blue button inside the manual page.
  const ocopLinks = sidebar?.querySelector('.sidebar-group[data-group="ocop"] .sidebar-group-links');
  if (ocopLinks) {
    const hubLink = ocopLinks.querySelector('a[href="/ocop/data-entry"]');
    const importLink = ocopLinks.querySelector('a[href="/ocop/import"]');
    const manualLink = ocopLinks.querySelector('a[href="/ocop/manual"]');
    const expiryLink = ocopLinks.querySelector('a[href="/ocop/expiry-alerts"]');
    const sourceLink = hubLink || manualLink || importLink;
    if (sourceLink && expiryLink) {
      const dataEntryLink = sourceLink.cloneNode(true);
      dataEntryLink.href = '/ocop/manual';
      dataEntryLink.title = 'Nhập dữ liệu';
      const label = dataEntryLink.querySelector('.sidebar-label');
      if (label) label.textContent = 'Nhập dữ liệu';
      const active = location.pathname === '/ocop/manual' || location.pathname.startsWith('/ocop/import') || location.pathname === '/ocop/data-entry';
      dataEntryLink.classList.toggle('active', active);
      if (active) dataEntryLink.setAttribute('aria-current', 'page');
      else dataEntryLink.removeAttribute('aria-current');
      hubLink?.remove();
      importLink?.remove();
      manualLink?.remove();
      ocopLinks.insertBefore(dataEntryLink, expiryLink);
    }
  }

  // Old hub links can remain in server-rendered breadcrumbs on older routes.
  // Point them back to the manual entry screen so the workflow stays direct.
  document.querySelectorAll('a[href="/ocop/data-entry"]').forEach(link => {
    link.href = '/ocop/manual';
  });

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
    role.querySelector('option[value="unit"]')?.remove();
    if (!['admin', 'staff'].includes(role.value)) role.value = 'staff';
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
