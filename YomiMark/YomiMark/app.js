(function() {
'use strict';

// ── STATE ─────────────────────────────────────────────────
var BM = [], FOLDERS = [], TABS = [];
var curView = 'all', curFolder = null, curQ = '', curSort = 'date-desc';
var viewMode = 'list'; // 'list' or 'grid'
var editingId = null;
var theme = 'default';

// ── THEMES ───────────────────────────────────────────────
var THEMES = [
  { id:'default', n:'Dark',   a:'#6c63ff', b:'#ff6b9d', s:'linear-gradient(135deg,#6c63ff,#ff6b9d)' },
  { id:'slate',   n:'Slate',  a:'#58a6ff', b:'#f78166', s:'linear-gradient(135deg,#58a6ff,#f78166)' },
  { id:'rose',    n:'Rose',   a:'#e879f9', b:'#fb7185', s:'linear-gradient(135deg,#e879f9,#fb7185)' },
  { id:'amber',   n:'Amber',  a:'#f59e0b', b:'#ef4444', s:'linear-gradient(135deg,#f59e0b,#ef4444)' },
  { id:'arctic',  n:'Light',  a:'#6366f1', b:'#ec4899', s:'linear-gradient(135deg,#6366f1,#ec4899)' },
  { id:'forest',  n:'Forest', a:'#22c55e', b:'#84cc16', s:'linear-gradient(135deg,#22c55e,#84cc16)' },
  { id:'ocean',   n:'Ocean',  a:'#38bdf8', b:'#818cf8', s:'linear-gradient(135deg,#38bdf8,#818cf8)' }
];

// ── HELPERS ───────────────────────────────────────────────
function ge(id) { return document.getElementById(id); }

function esc(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function host(u) {
  try { return new URL(u).hostname.replace(/^www\./, ''); } catch(e) { return ''; }
}

function fav(url) {
  var h = host(url);
  return h ? 'https://' + h + '/favicon.ico' : '';
}

function timeAgo(ts) {
  var diff = Date.now() - ts;
  var m = Math.floor(diff / 60000);
  var h = Math.floor(m / 60);
  var d = Math.floor(h / 24);
  if (d > 30) return new Date(ts).toLocaleDateString();
  if (d > 0) return d + 'd ago';
  if (h > 0) return h + 'h ago';
  if (m > 0) return m + 'm ago';
  return 'just now';
}

function getFolderName(folderId) {
  for (var i = 0; i < FOLDERS.length; i++) {
    if (FOLDERS[i].id === folderId) return FOLDERS[i].name;
  }
  return '';
}

// ── TOAST ─────────────────────────────────────────────────
function toast(msg, type) {
  var c = ge('toast-container');
  var el = document.createElement('div');
  el.className = 'toast ' + (type || 'info');
  el.innerHTML = '<div class="toast-dot"></div><span>' + esc(msg) + '</span>';
  c.appendChild(el);
  setTimeout(function() {
    el.classList.add('out');
    setTimeout(function() { el.remove(); }, 250);
  }, 2500);
}

// ── THEME ─────────────────────────────────────────────────
function applyTheme(id) {
  theme = id;
  document.documentElement.setAttribute('data-theme', id === 'default' ? '' : id);
  if (id === 'default') document.documentElement.removeAttribute('data-theme');
  else document.documentElement.setAttribute('data-theme', id);
  try { chrome.storage.local.set({ 'ym-theme': id }); } catch(e) {}
  buildThemeSwatches();
}

function buildThemeSwatches() {
  var c = ge('theme-swatches');
  if (!c) return;
  c.innerHTML = '';
  THEMES.forEach(function(t) {
    var sw = document.createElement('div');
    sw.className = 'tsw' + (t.id === theme ? ' on' : '');
    sw.style.background = t.s;
    sw.title = t.n;
    sw.addEventListener('click', function() { applyTheme(t.id); toast(t.n + ' theme applied', 'success'); });
    c.appendChild(sw);
  });
}

// ── SAVE / LOAD ───────────────────────────────────────────
function save() {
  try { chrome.storage.local.set({ 'ym-bm': BM, 'ym-folders': FOLDERS }); } catch(e) {}
}

function doSync(silent) {
  if (!silent) {
    ge('btnSync').innerHTML = '<span class="spin">↻</span> Syncing…';
    ge('btnSync').disabled = true;
  }
  chrome.bookmarks.getTree(function(tree) {
    if (chrome.runtime.lastError) {
      toast('Sync failed: ' + chrome.runtime.lastError.message, 'error');
      resetSyncBtn();
      return;
    }
    var bms = [], folders = [], seen = {};
    var SKIP = {'':1,'Bookmarks bar':1,'Other bookmarks':1,'Mobile bookmarks':1,
                'Bookmarks Bar':1,'Favorites bar':1,'Bookmarks':1,'Other':1};

    function walk(nodes, pf) {
      for (var i = 0; i < nodes.length; i++) {
        var n = nodes[i];
        if (n.url && !seen[n.url]) {
          seen[n.url] = 1;
          var fid = pf ? 'f_' + pf.replace(/\W/g,'_').slice(0,30) : '';
          // Preserve existing pin status
          var existing = null;
          for (var j = 0; j < BM.length; j++) { if (BM[j].url === n.url) { existing = BM[j]; break; } }
          bms.push({
            id: 'b' + n.id,
            title: n.title || n.url,
            url: n.url,
            folder: fid,
            pinned: existing ? existing.pinned : false,
            date: n.dateAdded || Date.now()
          });
        }
        if (n.children) {
          if (n.title && !SKIP[n.title]) {
            var folderId = 'f_' + n.title.replace(/\W/g,'_').slice(0,30);
            var exists = false;
            for (var k = 0; k < folders.length; k++) { if (folders[k].id === folderId) { exists = true; break; } }
            if (!exists) folders.push({ id: folderId, name: n.title });
            walk(n.children, n.title);
          } else walk(n.children, pf);
        }
      }
    }

    walk(tree, '');
    BM = bms;
    FOLDERS = folders;
    save();
    render();
    updateCounts();
    buildFolderList();
    resetSyncBtn();
    updateStatus('Synced ' + bms.length + ' bookmarks · ' + folders.length + ' folders');
    if (!silent) toast('Synced ' + bms.length + ' bookmarks', 'success');
  });
}

function resetSyncBtn() {
  ge('btnSync').disabled = false;
  ge('btnSync').innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/></svg> Sync';
}

function loadTabs() {
  chrome.tabs.query({}, function(tabs) {
    TABS = [];
    for (var i = 0; i < tabs.length; i++) {
      var t = tabs[i];
      if (t.url && !t.url.startsWith('chrome://') && !t.url.startsWith('chrome-extension://')) {
        TABS.push({ id:'t'+t.id, title:t.title||t.url||'Tab', url:t.url, pinned:false, date:Date.now() });
      }
    }
    ge('count-tabs').textContent = TABS.length;
    if (curView === 'tabs') render();
  });
}

// ── COUNTS ───────────────────────────────────────────────
function updateCounts() {
  ge('count-all').textContent = BM.length;
  ge('count-recent').textContent = Math.min(30, BM.length);
  ge('count-pinned').textContent = BM.filter(function(b){ return b.pinned; }).length;
}

// ── STATUS ───────────────────────────────────────────────
function updateStatus(msg) {
  ge('status-text').textContent = msg;
}

// ── FOLDER LIST ──────────────────────────────────────────
function buildFolderList() {
  var el = ge('folder-list');
  if (!FOLDERS.length) { el.innerHTML = '<div style="padding:4px 14px;font-size:11px;color:var(--text3)">No folders</div>'; return; }
  var html = '';
  FOLDERS.forEach(function(f) {
    var count = BM.filter(function(b){ return b.folder === f.id; }).length;
    html += '<div class="folder-item' + (curFolder === f.id ? ' active' : '') + '" data-fid="' + esc(f.id) + '">'
      + '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/></svg>'
      + '<span class="folder-name">' + esc(f.name) + '</span>'
      + '<span class="folder-count">' + count + '</span>'
      + '</div>';
  });
  el.innerHTML = html;

  el.querySelectorAll('.folder-item').forEach(function(item) {
    item.addEventListener('click', function() {
      var fid = this.getAttribute('data-fid');
      if (curFolder === fid) {
        curFolder = null;
        setView('all');
      } else {
        curFolder = fid;
        curView = 'folder';
        document.querySelectorAll('.nav-item').forEach(function(n){ n.classList.remove('active'); });
        buildFolderList();
        var fname = getFolderName(fid);
        ge('content-title').textContent = '📁 ' + fname;
        render();
      }
    });
  });
}

// ── VIEW ─────────────────────────────────────────────────
function setView(v) {
  curView = v;
  curFolder = null;
  document.querySelectorAll('.nav-item').forEach(function(n){ n.classList.remove('active'); });
  var navEl = ge('nav-' + v);
  if (navEl) navEl.classList.add('active');
  var titles = { all:'All Bookmarks', recent:'Recently Added', pinned:'Pinned', tabs:'Open Tabs' };
  ge('content-title').textContent = titles[v] || 'Bookmarks';
  buildFolderList();
  if (v === 'tabs') loadTabs();
  render();
}

// ── SORT & FILTER ────────────────────────────────────────
function getList() {
  var list;
  if (curView === 'tabs') return TABS.slice();
  if (curView === 'pinned') list = BM.filter(function(b){ return b.pinned; });
  else if (curView === 'recent') list = BM.slice().sort(function(a,b){ return b.date-a.date; }).slice(0,30);
  else if (curView === 'folder') list = BM.filter(function(b){ return b.folder === curFolder; });
  else list = BM.slice();

  if (curQ) {
    var q = curQ.toLowerCase();
    list = list.filter(function(b){
      return (b.title||'').toLowerCase().indexOf(q) >= 0 || (b.url||'').toLowerCase().indexOf(q) >= 0;
    });
  }

  // Sort
  if (curSort === 'alpha') list.sort(function(a,b){ return (a.title||'').localeCompare(b.title||''); });
  else if (curSort === 'alpha-desc') list.sort(function(a,b){ return (b.title||'').localeCompare(a.title||''); });
  else if (curSort === 'date-asc') list.sort(function(a,b){ return a.date-b.date; });
  else list.sort(function(a,b){ return b.date-a.date; });

  return list;
}

// ── RENDER ───────────────────────────────────────────────
function render() {
  var wrap = ge('list-wrap');
  var list = getList();

  if (!list.length) {
    var msg = curQ ? 'No results for "' + curQ + '"'
            : curView === 'pinned' ? 'No pinned bookmarks yet'
            : curView === 'tabs' ? 'No open tabs'
            : 'No bookmarks here';
    var sub = curQ ? 'Try different keywords' : curView === 'all' ? 'Click Sync to import from Chrome' : '';
    wrap.innerHTML = '<div class="empty-state">'
      + '<div class="empty-icon">' + (curQ ? '🔍' : '🔖') + '</div>'
      + '<div class="empty-title">' + msg + '</div>'
      + '<div class="empty-sub">' + sub + '</div>'
      + '</div>';
    updateStatus(curQ ? 'No results' : '0 items');
    return;
  }

  updateStatus(list.length + ' item' + (list.length !== 1 ? 's' : '') + (curQ ? ' matching "' + curQ + '"' : ''));

  if (viewMode === 'grid') {
    renderGrid(wrap, list);
  } else {
    renderList(wrap, list);
  }
}

function renderList(wrap, list) {
  // Group by folder if in 'all' view and no search
  var html = '<div class="bm-list">';
  if ((curView === 'all' || curView === 'recent') && !curQ) {
    var grouped = {}, ungrouped = [];
    list.forEach(function(b) {
      if (b.folder && getFolderName(b.folder)) {
        if (!grouped[b.folder]) grouped[b.folder] = [];
        grouped[b.folder].push(b);
      } else ungrouped.push(b);
    });
    ungrouped.forEach(function(b){ html += rowHTML(b); });
    Object.keys(grouped).forEach(function(fid) {
      var fname = getFolderName(fid);
      if (fname) {
        html += '<div class="folder-header-row"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/></svg>' + esc(fname) + '</div>';
        grouped[fid].forEach(function(b){ html += rowHTML(b); });
      }
    });
  } else {
    list.forEach(function(b){ html += rowHTML(b); });
  }
  html += '</div>';
  wrap.innerHTML = html;
  attachRowEvents(wrap);
}

function rowHTML(b) {
  var f = fav(b.url || '');
  var fname = b.folder ? getFolderName(b.folder) : '';
  return '<div class="bm-row' + (b.pinned ? ' pinned' : '') + '" data-id="' + esc(b.id) + '" data-url="' + esc(b.url||'') + '">'
    + '<div class="bm-fav">' + (f ? '<img src="' + esc(f) + '" onerror="this.style.display=\'none\'">' : '🌐') + '</div>'
    + '<div class="bm-body">'
      + '<div class="bm-title">' + esc(b.title || 'Untitled') + '</div>'
      + '<div class="bm-meta">'
        + '<span class="bm-domain">' + esc(host(b.url||'')) + '</span>'
        + (fname ? '<span class="bm-folder-tag">' + esc(fname) + '</span>' : '')
      + '</div>'
    + '</div>'
    + '<div class="bm-actions">'
      + '<button class="bm-action pin-btn" data-id="' + esc(b.id) + '" title="' + (b.pinned ? 'Unpin' : 'Pin') + '">' + (b.pinned ? '★' : '☆') + '</button>'
      + '<button class="bm-action edit-btn" data-id="' + esc(b.id) + '" title="Edit">✎</button>'
      + '<button class="bm-action del bm-del" data-id="' + esc(b.id) + '" title="Delete">✕</button>'
    + '</div>'
    + '</div>';
}

function renderGrid(wrap, list) {
  var html = '<div class="bm-grid">';
  list.forEach(function(b) {
    var f = fav(b.url || '');
    html += '<div class="bm-card" data-id="' + esc(b.id) + '" data-url="' + esc(b.url||'') + '">'
      + '<div class="bm-card-actions">'
        + '<button class="bm-action pin-btn" data-id="' + esc(b.id) + '">' + (b.pinned ? '★' : '☆') + '</button>'
        + '<button class="bm-action del bm-del" data-id="' + esc(b.id) + '">✕</button>'
      + '</div>'
      + '<div class="bm-card-fav">' + (f ? '<img src="' + esc(f) + '" onerror="this.style.display=\'none\'">' : '🌐') + '</div>'
      + '<div class="bm-card-title">' + esc(b.title || 'Untitled') + '</div>'
      + '<div class="bm-card-domain">' + esc(host(b.url||'')) + '</div>'
      + '</div>';
  });
  html += '</div>';
  wrap.innerHTML = html;
  attachRowEvents(wrap);
}

function attachRowEvents(wrap) {
  // Open bookmark
  wrap.querySelectorAll('.bm-row, .bm-card').forEach(function(row) {
    row.addEventListener('click', function(e) {
      if (e.target.closest('.bm-actions, .bm-card-actions, .bm-action')) return;
      var url = row.getAttribute('data-url');
      if (url) chrome.tabs.create({ url: url });
    });
  });

  // Pin
  wrap.querySelectorAll('.pin-btn').forEach(function(btn) {
    btn.addEventListener('click', function(e) {
      e.stopPropagation();
      var id = btn.getAttribute('data-id');
      togglePin(id);
    });
  });

  // Edit
  wrap.querySelectorAll('.edit-btn').forEach(function(btn) {
    btn.addEventListener('click', function(e) {
      e.stopPropagation();
      openEditModal(btn.getAttribute('data-id'));
    });
  });

  // Delete
  wrap.querySelectorAll('.bm-del').forEach(function(btn) {
    btn.addEventListener('click', function(e) {
      e.stopPropagation();
      deleteBookmark(btn.getAttribute('data-id'));
    });
  });
}

// ── BOOKMARK ACTIONS ─────────────────────────────────────
function findBM(id) {
  for (var i = 0; i < BM.length; i++) { if (BM[i].id === id) return BM[i]; }
  return null;
}

function togglePin(id) {
  var b = findBM(id);
  if (!b) return;
  b.pinned = !b.pinned;
  save();
  updateCounts();
  render();
  toast(b.pinned ? 'Pinned: ' + b.title : 'Unpinned', 'info');
}

function deleteBookmark(id) {
  var idx = -1;
  for (var i = 0; i < BM.length; i++) { if (BM[i].id === id) { idx = i; break; } }
  if (idx === -1) return;
  var title = BM[idx].title;
  BM.splice(idx, 1);
  save();
  updateCounts();
  buildFolderList();
  render();
  toast('Deleted: ' + title, 'error');
}

// ── MODAL ────────────────────────────────────────────────
function updateFolderSelect() {
  var sel = ge('m-folder');
  sel.innerHTML = '<option value="">No folder</option>';
  FOLDERS.forEach(function(f) {
    var opt = document.createElement('option');
    opt.value = f.id;
    opt.textContent = f.name;
    sel.appendChild(opt);
  });
}

function openAddModal() {
  editingId = null;
  ge('modal-title').textContent = 'Add Bookmark';
  ge('modal-sub').textContent = 'Save a page to your collection';
  ge('btnSave').textContent = 'Save Bookmark';
  ge('m-title').value = '';
  ge('m-url').value = '';
  ge('m-folder').value = '';
  updateFolderSelect();
  chrome.tabs.query({ active: true, currentWindow: true }, function(tabs) {
    if (tabs && tabs[0]) {
      ge('m-title').value = tabs[0].title || '';
      ge('m-url').value   = tabs[0].url   || '';
    }
  });
  ge('overlay').classList.add('open');
  setTimeout(function(){ ge('m-title').focus(); }, 80);
}

function openEditModal(id) {
  var b = findBM(id);
  if (!b) return;
  editingId = id;
  ge('modal-title').textContent = 'Edit Bookmark';
  ge('modal-sub').textContent = 'Update title, URL or folder';
  ge('btnSave').textContent = 'Save Changes';
  updateFolderSelect();
  ge('m-title').value  = b.title || '';
  ge('m-url').value    = b.url   || '';
  ge('m-folder').value = b.folder || '';
  ge('overlay').classList.add('open');
  setTimeout(function(){ ge('m-title').focus(); }, 80);
}

function closeModal() { ge('overlay').classList.remove('open'); editingId = null; }

function saveModal() {
  var title  = ge('m-title').value.trim();
  var url    = ge('m-url').value.trim();
  var folder = ge('m-folder').value;
  if (!title || !url) { toast('Title and URL are required', 'error'); return; }

  if (editingId) {
    var b = findBM(editingId);
    if (b) { b.title = title; b.url = url; b.folder = folder; }
    save(); render(); closeModal(); toast('Bookmark updated', 'success');
  } else {
    var nb = { id:'ym'+Date.now(), title:title, url:url, folder:folder, pinned:false, date:Date.now() };
    BM.unshift(nb);
    try { chrome.bookmarks.create({ title:title, url:url }); } catch(e){}
    save(); updateCounts(); buildFolderList(); render(); closeModal();
    toast('Bookmark saved', 'success');
  }
}

// ── KEYBOARD SHORTCUTS ───────────────────────────────────
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') { closeModal(); }
  if ((e.ctrlKey || e.metaKey) && e.key === 'f') { e.preventDefault(); ge('search').focus(); }
  if ((e.ctrlKey || e.metaKey) && e.key === 'n') { e.preventDefault(); openAddModal(); }
  if ((e.ctrlKey || e.metaKey) && e.key === 'r') { e.preventDefault(); doSync(false); }
});

// ── INIT ─────────────────────────────────────────────────
function init() {
  buildThemeSwatches();

  // Load from storage first (instant)
  chrome.storage.local.get(['ym-theme','ym-bm','ym-folders'], function(r) {
    if (r['ym-theme']) applyTheme(r['ym-theme']);

    if (r['ym-bm'] && r['ym-bm'].length) {
      BM = r['ym-bm'];
      FOLDERS = r['ym-folders'] || [];
      updateCounts();
      buildFolderList();
      render();
      updateStatus('Loaded ' + BM.length + ' bookmarks from cache');
    } else {
      doSync(true);
    }
  });

  loadTabs();

  // Nav items
  document.querySelectorAll('.nav-item').forEach(function(item) {
    item.addEventListener('click', function() {
      setView(item.getAttribute('data-view'));
    });
  });

  // Search
  ge('search').addEventListener('input', function() {
    curQ = this.value.trim();
    ge('searchClear').classList.toggle('show', curQ.length > 0);
    render();
  });
  ge('searchClear').addEventListener('click', function() {
    ge('search').value = ''; curQ = '';
    this.classList.remove('show');
    ge('search').focus(); render();
  });

  // Sort
  ge('sortSelect').addEventListener('change', function() {
    curSort = this.value; render();
  });

  // View toggle
  ge('vbtn-list').addEventListener('click', function() {
    viewMode = 'list';
    ge('vbtn-list').classList.add('on');
    ge('vbtn-grid').classList.remove('on');
    render();
  });
  ge('vbtn-grid').addEventListener('click', function() {
    viewMode = 'grid';
    ge('vbtn-grid').classList.add('on');
    ge('vbtn-list').classList.remove('on');
    render();
  });

  // Sync
  ge('btnSync').addEventListener('click', function(e) { e.stopPropagation(); doSync(false); });

  // Add
  ge('btnAdd').addEventListener('click', function(e) { e.stopPropagation(); openAddModal(); });

  // Close
  ge('btnClose').addEventListener('click', function() { window.close(); });

  // Modal
  ge('btnCancel').addEventListener('click', function(e) { e.stopPropagation(); closeModal(); });
  ge('btnSave').addEventListener('click', function(e) { e.stopPropagation(); saveModal(); });
  ge('modal').addEventListener('click', function(e) { e.stopPropagation(); });
  ge('overlay').addEventListener('click', function() { closeModal(); });

  // Enter to save modal
  ['m-title','m-url'].forEach(function(id) {
    ge(id).addEventListener('keydown', function(e) { if (e.key === 'Enter') saveModal(); });
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

})();
