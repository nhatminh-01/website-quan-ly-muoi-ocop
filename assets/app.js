(() => {
  const header = document.querySelector('.site-header');
  const menu = document.getElementById('sidebar-toggle');
  const sidebar = document.getElementById('site-sidebar');
  const main = document.getElementById('main-content');
  const backdrop = document.getElementById('sidebar-backdrop');
  const mobile = window.matchMedia('(max-width: 900px)');
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
      sidebar?.querySelector('input, a, button')?.focus();
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
})();
