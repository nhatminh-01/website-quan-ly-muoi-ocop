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

  // Keep the two-module home overview visually centered as one balanced block.
  const moduleGrid = document.querySelector('.module-grid');
  if (moduleGrid) {
    moduleGrid.style.marginInline = 'auto';
    const pageHead = moduleGrid.previousElementSibling;
    if (pageHead?.classList.contains('page-head')) {
      pageHead.style.maxWidth = '1180px';
      pageHead.style.marginLeft = 'auto';
      pageHead.style.marginRight = 'auto';
    }
  }

  // Home is an operational snapshot for the two datasets, not just a pair of links.
  function installOverviewStyles() {
    if (document.getElementById('home-overview-styles')) return;
    const style = document.createElement('style');
    style.id = 'home-overview-styles';
    style.textContent = `
      .module-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;padding:15px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
      .module-kpi{min-width:0;padding-right:8px;border-right:1px solid #edf0f3}
      .module-kpi:last-child{border-right:0;padding-right:0}
      .module-kpi strong{display:block;color:var(--primary);font-size:20px;line-height:1.25;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
      .module-kpi strong.compact{font-size:13px;line-height:1.4;white-space:normal;overflow-wrap:normal;word-break:normal}
      .module-kpi span{display:block;color:var(--muted);font-size:11px;line-height:1.4;margin-top:4px}
      .module-kpi small{display:block;color:#8792a1;font-size:10px;line-height:1.35;margin-top:3px}
      .module-overview-note{display:flex;align-items:center;gap:7px;margin:13px 0 0;color:#738094;font-size:11px}
      .legacy-unit-account{opacity:.74;background:#fafafa}
      .legacy-unit-account td:nth-child(2){color:#8b5b3d;font-weight:650}
      .chi-cuc-only-note{margin-bottom:16px}
      @media(max-width:1150px){.module-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.module-kpi:nth-child(2){border-right:0}.module-kpi:nth-child(-n+2){padding-bottom:8px;border-bottom:1px solid #edf0f3}}
      @media(max-width:620px){.module-kpis{grid-template-columns:1fr}.module-kpi{border-right:0!important;border-bottom:1px solid #edf0f3;padding:0 0 9px!important}.module-kpi:last-child{border-bottom:0;padding-bottom:0!important}}
    `;
    document.head.appendChild(style);
  }

  function renderKpis(card, items) {
    const stats = card?.querySelector('.module-stats, .module-kpis');
    if (!stats) return;
    stats.className = 'module-kpis';
    stats.replaceChildren();
    items.forEach(item => {
      const box = document.createElement('div');
      box.className = 'module-kpi';
      const strong = document.createElement('strong');
      strong.textContent = item.value ?? '—';
      if (item.compact) strong.classList.add('compact');
      const label = document.createElement('span');
      label.textContent = item.label;
      box.append(strong, label);
      if (item.detail) {
        const detail = document.createElement('small');
        detail.textContent = item.detail;
        box.append(detail);
      }
      stats.append(box);
    });
  }

  async function fetchDocument(url) {
    const response = await fetch(url, { credentials: 'same-origin', headers: { 'X-Requested-With': 'home-overview' } });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return new DOMParser().parseFromString(await response.text(), 'text/html');
  }

  function parseVietnameseNumber(value) {
    let token = String(value ?? '').trim().replace(/\s+/g, '');
    if (!token || token === '-' || token === '—') return null;
    token = token.replace(/[^0-9,.-]/g, '');
    if (!token) return null;
    if (token.includes('.') && token.includes(',')) {
      token = token.lastIndexOf(',') > token.lastIndexOf('.')
        ? token.replace(/\./g, '').replace(',', '.')
        : token.replace(/,/g, '');
    } else if (/^-?\d{1,3}(?:\.\d{3})+$/.test(token)) {
      token = token.replace(/\./g, '');
    } else if (token.includes(',')) {
      token = token.replace(',', '.');
    }
    const number = Number(token);
    return Number.isFinite(number) ? number : null;
  }

  function weeklyWarningRows(doc) {
    const rows = [...doc.querySelectorAll('.excel-sheet tbody tr:not(.sheet-total)')];
    const groups = [[2, 3, 4], [5, 6, 7], [8, 9, 10], [11, 12, 13], [14, 15, 16], [22, 23, 24]];
    return rows.reduce((count, row) => {
      const cells = [...row.querySelectorAll('td')];
      const warning = groups.some(([totalIndex, leftIndex, rightIndex]) => {
        const total = parseVietnameseNumber(cells[totalIndex]?.textContent);
        if (total === null) return false;
        const left = parseVietnameseNumber(cells[leftIndex]?.textContent) ?? 0;
        const right = parseVietnameseNumber(cells[rightIndex]?.textContent) ?? 0;
        return Math.abs(total - left - right) > 0.01;
      });
      return count + (warning ? 1 : 0);
    }, 0);
  }

  function totalFromPagination(doc) {
    const text = doc.querySelector('.ocop-pagination .muted')?.textContent || '';
    const match = text.match(/\/\s*([\d.]+)/);
    return match ? Number(match[1].replace(/\./g, '')) : 0;
  }

  function shortTimestamp(value) {
    const text = String(value || '').trim();
    const match = text.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}:\d{2})/);
    return match ? `${match[3]}/${match[2]}/${match[1]} ${match[4]}` : (text || '—');
  }

  async function enhanceHomeOverview() {
    if (!moduleGrid) return;
    installOverviewStyles();
    const cards = [...moduleGrid.querySelectorAll('.module-card')];
    if (cards.length < 2) return;
    const saltCard = cards[0];
    const ocopCard = cards[1];
    const saltExisting = [...saltCard.querySelectorAll('.module-stats strong')].map(el => el.textContent.trim());
    const ocopExisting = [...ocopCard.querySelectorAll('.module-stats strong')].map(el => el.textContent.trim());
    const saltSheets = saltExisting[0] || '0';
    const ocopEntities = ocopExisting[0] || '0';
    const ocopProducts = ocopExisting[1] || '0';

    const saltDescription = saltCard.querySelector('p');
    const ocopDescription = ocopCard.querySelector('p');
    if (saltDescription) saltDescription.textContent = 'Tổng quan kỳ báo cáo mới nhất, tình trạng dữ liệu và tra cứu số liệu Diêm nghiệp tập trung tại Chi cục.';
    if (ocopDescription) ocopDescription.textContent = 'Tổng quan danh mục sản phẩm, chủ thể, hạng sao và thời điểm cập nhật dữ liệu OCOP.';

    renderKpis(saltCard, [
      { value: '…', label: 'Kỳ báo cáo mới nhất' },
      { value: '…', label: 'Xã/phường có dữ liệu' },
      { value: '…', label: 'Dòng cảnh báo' },
      { value: saltSheets, label: 'Tổng sheet đã nhập' },
    ]);
    renderKpis(ocopCard, [
      { value: ocopProducts, label: 'Tổng sản phẩm' },
      { value: ocopEntities, label: 'Tổng chủ thể' },
      { value: '…', label: 'Phân bố hạng sao', compact: true },
      { value: '…', label: 'Cập nhật gần nhất', compact: true },
    ]);

    try {
      const weeklyDoc = await fetchDocument('/records?view=full');
      const meta = {};
      weeklyDoc.querySelectorAll('.sheet-meta>div').forEach(item => {
        const key = item.querySelector('span')?.textContent.trim();
        const value = item.querySelector('strong')?.textContent.trim();
        if (key) meta[key] = value || '—';
      });
      renderKpis(saltCard, [
        { value: meta['Tuần'] || '—', label: 'Kỳ báo cáo mới nhất', detail: meta['Số liệu đến ngày'] ? `Số liệu đến ${meta['Số liệu đến ngày']}` : '' },
        { value: meta['Số xã/phường'] || '0', label: 'Xã/phường có dữ liệu' },
        { value: String(weeklyWarningRows(weeklyDoc)), label: 'Dòng cảnh báo' },
        { value: saltSheets, label: 'Tổng sheet đã nhập' },
      ]);
    } catch (_) {
      renderKpis(saltCard, [
        { value: '—', label: 'Kỳ báo cáo mới nhất' },
        { value: '—', label: 'Xã/phường có dữ liệu' },
        { value: '—', label: 'Dòng cảnh báo' },
        { value: saltSheets, label: 'Tổng sheet đã nhập' },
      ]);
    }

    try {
      const [star3Doc, star4Doc, star5Doc, importDoc] = await Promise.all([
        fetchDocument('/ocop?star=3&page_size=1'),
        fetchDocument('/ocop?star=4&page_size=1'),
        fetchDocument('/ocop?star=5&page_size=1'),
        fetchDocument('/ocop/import'),
      ]);
      const stars = `3★: ${totalFromPagination(star3Doc)} | 4★: ${totalFromPagination(star4Doc)} | 5★: ${totalFromPagination(star5Doc)}`;
      const historyTable = [...importDoc.querySelectorAll('table')].find(table => table.textContent.includes('Người import') && table.textContent.includes('Thời gian'));
      const cells = historyTable ? [...(historyTable.querySelector('tbody tr')?.querySelectorAll('td') || [])] : [];
      const latest = cells.length >= 9 ? shortTimestamp(cells[8].textContent) : '—';
      renderKpis(ocopCard, [
        { value: ocopProducts, label: 'Tổng sản phẩm' },
        { value: ocopEntities, label: 'Tổng chủ thể' },
        { value: stars, label: 'Phân bố hạng sao', compact: true },
        { value: latest, label: 'Cập nhật gần nhất', compact: true },
      ]);
    } catch (_) {
      renderKpis(ocopCard, [
        { value: ocopProducts, label: 'Tổng sản phẩm' },
        { value: ocopEntities, label: 'Tổng chủ thể' },
        { value: '—', label: 'Phân bố hạng sao', compact: true },
        { value: '—', label: 'Cập nhật gần nhất', compact: true },
      ]);
    }
  }
  enhanceHomeOverview();

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