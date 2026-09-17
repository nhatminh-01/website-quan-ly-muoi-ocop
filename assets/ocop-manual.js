(() => {
  const form = document.querySelector('[data-ocop-manual]');
  if (!form) return;
  const list = form.querySelector('[data-recognition-list]');
  const add = form.querySelector('[data-add-recognition]');
  const refresh = () => {
    const rows = [...list.querySelectorAll('[data-recognition]')];
    rows.forEach((row, index) => {
      row.querySelector('[data-recognition-number]').textContent = index + 1;
      row.querySelectorAll('[name], [id], label[for]').forEach(field => {
        for (const attribute of ['name', 'id', 'for']) {
          if (field.hasAttribute(attribute)) field.setAttribute(attribute,
            field.getAttribute(attribute).replace(/recognition_\d+_/, `recognition_${index}_`));
        }
      });
      row.querySelector('[data-remove-recognition]').disabled = rows.length === 1;
    });
    add.disabled = rows.length >= 50;
  };
  add.addEventListener('click', () => {
    if (list.children.length >= 50) return;
    list.append(form.querySelector('[data-recognition-template]').content.cloneNode(true));
    refresh();
    list.lastElementChild.querySelector('select').focus();
  });
  list.addEventListener('click', event => {
    const button = event.target.closest('[data-remove-recognition]');
    if (!button || list.children.length <= 1) return;
    button.closest('[data-recognition]').remove();
    refresh();
    add.focus();
  });
  refresh();
})();
