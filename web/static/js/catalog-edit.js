// catalog-edit.js
let draggedItem = null;
let activeCategoryId = null;
let activeSubcategoryId = null;

function showToast(message) {
  const toast = document.getElementById('toast');
  toast.textContent = message;
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 3000);
}

function switchTab(tab) {
  document.querySelectorAll('.tab-button').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === tab);
  });
  document.querySelectorAll('.view-container').forEach(c => {
    c.classList.toggle('active', c.id === 'tab-' + tab);
  });
}

function buildCategoryTree(flatList, parentId = null, level = 0) {
  return flatList
    .filter(cat => cat.parent_id == parentId)
    .map(cat => ({
      ...cat,
      level,
      children: buildCategoryTree(flatList, cat.id, level + 1)
    }));
}

function renderTree(container, nodes, clickHandler) {
  container.innerHTML = '';
  nodes.forEach(node => {
    const el = document.createElement('div');
    el.className = 'item';
    el.draggable = true;
    el.dataset.id = node.id;
    el.dataset.level = node.level;
    el.style.marginLeft = `${node.level * 20}px`;
    el.innerHTML = `
      <span class="item-name" ${clickHandler ? `onclick=\"${clickHandler.name}(${node.id}, this)\"` : ''}>
        ${node.level > 0 ? '↳ ' : ''}${node.name}
      </span>
      <span>
        <button class="icon-button" onclick="editItem(event, ${node.id}, 'category')">✏️</button>
        <button class="icon-button" onclick="deleteItem(event, ${node.id}, 'category')">🗑️</button>
      </span>
    `;
    container.appendChild(el);
    if (node.children && node.children.length > 0) {
      renderTree(container, node.children, clickHandler);
    }
  });
}

function renderCategories() {
  fetch('/catalog/categories-json')
    .then(res => res.json())
    .then(data => {
      window.categories = data;
      const tree = buildCategoryTree(data);
      renderTree(document.getElementById('categories'), tree, selectCategory);
      if (tree.length > 0) selectCategory(tree[0].id);
    });
}

function selectCategory(id, el) {
  activeCategoryId = id;
  activeSubcategoryId = null;
  document.querySelectorAll('#categories .item').forEach(i => i.classList.remove('active'));
  if (el && el.closest('.item')) el.closest('.item').classList.add('active');

  const tree = buildCategoryTree(window.categories, id, 1);
  renderTree(document.getElementById('subcategories'), tree, selectSubcategory);

  fetch(`/catalog/brands/${id}`).then(r => r.json()).then(data => {
    renderList('brands', data.brands);
  });
}


function selectSubcategory(id, el) {
  activeSubcategoryId = id;
  document.querySelectorAll('#subcategories .item').forEach(i => i.classList.remove('active'));
  if (el && el.closest('.item')) el.closest('.item').classList.add('active');
  fetch(`/catalog/brands/${id}`).then(r => r.json()).then(data => {
    renderList('brands', data.brands);
  });
}

function renderList(containerId, items, clickHandler) {
  const container = document.getElementById(containerId);
  container.innerHTML = '';
  items.forEach(item => {
    const el = document.createElement('div');
    el.className = 'item';
    el.draggable = true;
    el.dataset.id = item.id;
    el.innerHTML = `
      <span class="item-name" ${clickHandler ? `onclick=\"${clickHandler.name}(${item.id}, this)\"` : ''}>${item.name}</span>
      <span>
        <button class="icon-button" onclick="editItem(event, ${item.id}, '${containerId.slice(0, -1)}')">✏️</button>
        <button class="icon-button" onclick="deleteItem(event, ${item.id}, '${containerId.slice(0, -1)}')">🗑️</button>
      </span>
    `;
    container.appendChild(el);
  });
}

function editItem(e, id, type) {
  e.stopPropagation();
  alert(`✏️ Редактировать ${type} ${id}`);
}

function deleteItem(e, id, type) {
  e.stopPropagation();
  if (!confirm(`Удалить ${type}?`)) return;
  fetch(`/catalog/delete/${type}/${id}`, { method: 'DELETE' })
    .then(() => {
      showToast(`${type} удалён`);
      renderCategories();
    });
}

function addCategory() {
  const container = document.getElementById('categories');
  const form = document.createElement('div');
  form.className = 'inline-form';
  form.innerHTML = `<input type="text" placeholder="Новая категория"><button>📋</button>`;
  form.querySelector('button').onclick = () => {
    const name = form.querySelector('input').value.trim();
    if (!name) return;
    fetch('/catalog/edit/add-category', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ name })
    }).then(() => renderCategories());
  };
  container.prepend(form);
}

function addSubcategory() {
  const container = document.getElementById('subcategories');
  const form = document.createElement('div');
  form.className = 'inline-form';
  form.innerHTML = `<input type="text" placeholder="Новая подкатегория"><button>📋</button>`;
  form.querySelector('button').onclick = () => {
    const name = form.querySelector('input').value.trim();
    const parentId = activeSubcategoryId || activeCategoryId;
    if (!name || !parentId) return;
    fetch('/catalog/edit/add-category', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ name, parent_id: parentId })
    }).then(() => renderCategories());
  };
  container.prepend(form);
}

function addBrandToCategory() {
  const container = document.getElementById('brands');
  const form = document.createElement('div');
  form.className = 'inline-form';
  form.innerHTML = `<input type="text" placeholder="Новый бренд"><button>📋</button>`;
  form.querySelector('button').onclick = () => {
    const name = form.querySelector('input').value.trim();
    if (!name || !activeCategoryId) return;
    fetch('/catalog/edit/add-brand', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ name, category_id: activeCategoryId })
    }).then(() => selectCategory(activeCategoryId));
  };
  container.prepend(form);
}

function enableDragDrop(containerId, onDropCallback, allowCrossDrop = false, acceptFrom = []) {
  const container = document.getElementById(containerId);
  container.addEventListener('dragstart', e => {
    if (e.target.classList.contains('item')) {
      draggedItem = e.target;
      e.dataTransfer.setData('text/plain', containerId);
      e.dataTransfer.setData('item-id', draggedItem.dataset.id);
      e.target.classList.add('dragging');
    }
  });

  container.addEventListener('dragend', () => {
    draggedItem = null;
    document.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));
    document.querySelectorAll('.dragging').forEach(el => el.classList.remove('dragging'));
  });

  container.addEventListener('dragover', e => {
    e.preventDefault();
    const target = e.target.closest('.item');
    if (target && target !== draggedItem) {
      document.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));
      target.classList.add('drag-over');
    }
  });

  container.addEventListener('drop', e => {
    e.preventDefault();
    const sourceId = e.dataTransfer.getData('text/plain');
    const sourceItemId = e.dataTransfer.getData('item-id');
    const target = e.target.closest('.item');

    const targetId = target?.dataset?.id || activeCategoryId;

    if (target && draggedItem && draggedItem !== target) {
      container.insertBefore(draggedItem, target);
    } else if (!target && draggedItem) {
      container.appendChild(draggedItem);
    }

    if ((containerId === 'subcategories' && sourceId === 'categories') ||
        (containerId === 'subcategories' && sourceId === 'subcategories')) {
      fetch('/catalog/move-category', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ category_id: sourceItemId, new_parent_id: targetId })
      })
        .then(() => fetch('/catalog/categories-json'))
        .then(res => res.json())
        .then(data => {
          window.categories = data;
          renderCategories();
          showToast('Категория перемещена');
        });
    } else if (containerId === 'categories' && sourceId === 'subcategories') {
      fetch('/catalog/move-category', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ category_id: sourceItemId, new_parent_id: '' })
      })
        .then(() => fetch('/catalog/categories-json'))
        .then(res => res.json())
        .then(data => {
          window.categories = data;
          renderCategories();
          showToast('Подкатегория перемещена в корень');
        });
    }

    onDropCallback();
  });
}

window.addEventListener('DOMContentLoaded', () => {
  renderCategories();
  ['categories', 'subcategories', 'brands'].forEach(id => enableDragDrop(id, () => saveNewOrder(id), true, ['categories', 'subcategories']));
});

function saveNewOrder(containerId) {
  const container = document.getElementById(containerId);
  const ids = Array.from(container.querySelectorAll('.item')).map(el => el.dataset.id);
  fetch(`/catalog/reorder/${containerId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids })
  }).then(() => showToast('Порядок сохранён'));
}
