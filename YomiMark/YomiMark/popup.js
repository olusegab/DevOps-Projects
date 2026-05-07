(function() {

var BM = [], FOLDERS = [], TABS = [];
var curView = 'all', curQ = '', theme = 'midnight';
var panelOpen = false;

var THEMES = [
  { id: 'midnight', n: 'Night',  a: '#7c6aff', b: '#ff6ab0' },
  { id: 'aurora',   n: 'Aurora', a: '#00dfa0', b: '#00b8d4' },
  { id: 'crimson',  n: 'Red',    a: '#ff3d60', b: '#ff8c35' },
  { id: 'ocean',    n: 'Ocean',  a: '#00b0d8', b: '#40c8e4' },
  { id: 'solar',    n: 'Solar',  a: '#f0a020', b: '#ff5e30' },
  { id: 'sakura',   n: 'Pink',   a: '#ff7ab8', b: '#c070ff' },
  { id: 'arctic',   n: 'Light',  a: '#1e5ce8', b: '#7030e0' },
  { id: 'forest',   n: 'Green',  a: '#40d870', b: '#80e8a0' },
  { id: 'galaxy',   n: 'Galaxy', a: '#9a80fa', b: '#f060b8' },
  { id: 'neon',     n: 'Neon',   a: '#00ffcc', b: '#ff00aa' },
  { id: 'ember',    n: 'Ember',  a: '#ff6000', b: '#ff8e00' }
];

var THEME_CSS = {
  midnight: '',
  aurora:   '--bg:#061410;--bg2:#0c1e18;--bg3:#132820;--card:#0e1c18;--bdr:#1a4030;--a:#00dfa0;--a2:#00b8d4;--t:#dffff5;--t2:#5aaa88;--t3:#1e5040',
  crimson:  '--bg:#110808;--bg2:#1c0e0e;--bg3:#281414;--card:#180c0c;--bdr:#381818;--a:#ff3d60;--a2:#ff8c35;--t:#fff0f0;--t2:#bb7070;--t3:#5a2828',
  ocean:    '--bg:#04101a;--bg2:#081822;--bg3:#0e2232;--card:#0a1820;--bdr:#0e2838;--a:#00b0d8;--a2:#40c8e4;--t:#ddf4ff;--t2:#4488a8;--t3:#183848',
  solar:    '--bg:#160f00;--bg2:#221800;--bg3:#2e2100;--card:#1e1600;--bdr:#382400;--a:#f0a020;--a2:#ff5e30;--t:#fff6dc;--t2:#ba8820;--t3:#604000',
  sakura:   '--bg:#16090f;--bg2:#200f1a;--bg3:#2c1525;--card:#1c0e18;--bdr:#361628;--a:#ff7ab8;--a2:#c070ff;--t:#fff0f8;--t2:#bb70a0;--t3:#5e2848',
  arctic:   '--bg:#edf2f8;--bg2:#e0e8f2;--bg3:#d4deec;--card:#fff;--bdr:#c0cee0;--a:#1e5ce8;--a2:#7030e0;--t:#0a1828;--t2:#3a5070;--t3:#8090a8',
  forest:   '--bg:#060e04;--bg2:#0c1808;--bg3:#121e10;--card:#0a1608;--bdr:#162c14;--a:#40d870;--a2:#80e8a0;--t:#eeffee;--t2:#50a060;--t3:#204830',
  galaxy:   '--bg:#04040e;--bg2:#08081c;--bg3:#0e0e2a;--card:#080820;--bdr:#1a1a50;--a:#9a80fa;--a2:#f060b8;--t:#f0eeff;--t2:#7060c0;--t3:#303080',
  neon:     '--bg:#050510;--bg2:#09091e;--bg3:#0f0f2c;--card:#08081a;--bdr:#202060;--a:#00ffcc;--a2:#ff00aa;--t:#f0fff8;--t2:#40a880;--t3:#204850',
  ember:    '--bg:#100600;--bg2:#1c0c00;--bg3:#281200;--card:#180a00;--bdr:#381400;--a:#ff6000;--a2:#ff8e00;--t:#fff6ee;--t2:#b86820;--t3:#583000'
};

function ge(id) { return document.getElementById(id); }

function toast(msg) {
  var el = ge('toast');
  el.textContent = msg;
  el.classList.add('show');
  setTimeout(function() { el.classList.remove('show'); }, 2200);
}

function esc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function host(u) {
  try { return new URL(u).hostname.replace(/^www\./, ''); } catch(e) { return ''; }
}

// ── THEME ──────────────────────────────────────────────────────
function applyTheme(id) {
  theme = id;
  var vars = THEME_CSS[id] || '';
  if (vars) {
    document.body.setAttribute('style', vars.split(';').map(function(v) {
      var p = v.trim().split(':');
      return p.length === 2 ? p[0].trim() + ':' + p[1].trim() : '';
    }).filter(Boolean).map(function(v) { return v; }).join(';'));
  } else {
    document.body.removeAttribute('style');
  }
  try { chrome.storage.local.set({ 'ym-theme': id }); } catch(e) {}
  buildGrid();
}

function buildGrid() {
  var g = ge('tgrid');
  if (!g) return;
  g.innerHTML = '';
  for (var i = 0; i < THEMES.length; i++) {
    var t = THEMES[i];
    var sw = document.createElement('div');
    sw.className = 'tsw' + (t.id === theme ? ' on' : '');
    sw.style.background = 'linear-gradient(135deg,' + t.a + ',' + t.b + ')';
    sw.setAttribute('data-id', t.id);
    var sp = document.createElement('span');
    sp.textContent = t.n;
    sw.appendChild(sp);
    g.appendChild(sw);
    sw.addEventListener('click', (function(tid, tn) {
      return function(e) {
        e.stopPropagation();
        applyTheme(tid);
        toast(tn + ' theme');
      };
    })(t.id, t.n));
  }
}

// ── RENDER ─────────────────────────────────────────────────────
function render() {
  var el = ge('list');
  var stat = ge('stat');
  if (!el) return;

  stat.innerHTML = '<b>' + BM.length + '</b> bookmarks';

  var list;
  if (curView === 'tabs') {
    list = TABS.slice();
  } else if (curView === 'recent') {
    list = BM.slice().sort(function(a, b) { return b.date - a.date; }).slice(0, 30);
  } else {
    list = BM.slice();
  }

  if (curQ) {
    var q = curQ.toLowerCase();
    list = list.filter(function(b) {
      return (b.title || '').toLowerCase().indexOf(q) >= 0 ||
             (b.url  || '').toLowerCase().indexOf(q) >= 0;
    });
  }

  if (!list.length) {
    el.innerHTML = '<div class="empty">' +
      '<div class="empty-icon">' + (curQ ? '&#128269;' : '&#128278;') + '</div>' +
      '<div class="empty-title">' + (curQ ? 'No results' : curView === 'tabs' ? 'No open tabs' : 'No bookmarks') + '</div>' +
      '<div class="empty-sub">' + (curQ ? 'Try different keywords' : 'Press the sync button &#8635; above') + '</div>' +
      '</div>';
    return;
  }

  // Group by folder for 'all' view
  var html = '';
  if (curView === 'all' && !curQ) {
    var grouped = {};
    var ungrouped = [];
    for (var i = 0; i < list.length; i++) {
      var b = list[i];
      var found = null;
      for (var j = 0; j < FOLDERS.length; j++) {
        if (FOLDERS[j].id === b.folder) { found = FOLDERS[j]; break; }
      }
      if (found) {
        if (!grouped[found.id]) grouped[found.id] = [];
        grouped[found.id].push(b);
      } else {
        ungrouped.push(b);
      }
    }
    for (var k = 0; k < ungrouped.length; k++) html += makeRow(ungrouped[k]);
    var keys = Object.keys(grouped);
    for (var m = 0; m < keys.length; m++) {
      var fo = null;
      for (var n = 0; n < FOLDERS.length; n++) {
        if (FOLDERS[n].id === keys[m]) { fo = FOLDERS[n]; break; }
      }
      if (fo) {
        html += '<div class="flabel">&#128193; ' + esc(fo.name) + '</div>';
        for (var p = 0; p < grouped[keys[m]].length; p++) html += makeRow(grouped[keys[m]][p]);
      }
    }
  } else {
    for (var r = 0; r < list.length; r++) html += makeRow(list[r]);
  }

  el.innerHTML = html;

  var rows = el.querySelectorAll('.brow');
  for (var x = 0; x < rows.length; x++) {
    (function(row) {
      row.addEventListener('click', function() {
        var url = row.getAttribute('data-url');
        if (url) {
          try { chrome.tabs.create({ url: url }); } catch(e) { window.open(url, '_blank'); }
        }
      });
    })(rows[x]);
  }
}

function makeRow(b) {
  var h = host(b.url || '');
  var fav = h ? 'https://' + h + '/favicon.ico' : '';
  return '<div class="brow" data-url="' + esc(b.url || '') + '">' +
    '<div class="bfav">' +
      (fav ? '<img src="' + esc(fav) + '" onerror="this.style.display=\'none\'">' : '&#127760;') +
    '</div>' +
    '<div class="binfo">' +
      '<div class="btitle">' + esc(b.title || 'Untitled') + '</div>' +
      '<div class="burl">' + esc(h) + '</div>' +
    '</div>' +
    '</div>';
}

// ── SYNC ───────────────────────────────────────────────────────
function doSync(silent) {
  if (!silent) toast('Syncing...');
  chrome.bookmarks.getTree(function(tree) {
    if (chrome.runtime.lastError) {
      toast('Sync failed: ' + chrome.runtime.lastError.message);
      return;
    }
    var bms = [], folders = [], seen = {};
    var skip = { '': 1, 'Bookmarks bar': 1, 'Other bookmarks': 1,
                 'Mobile bookmarks': 1, 'Bookmarks Bar': 1,
                 'Favorites bar': 1, 'Bookmarks': 1, 'Other': 1 };

    function walk(nodes, pf) {
      for (var i = 0; i < nodes.length; i++) {
        var n = nodes[i];
        if (n.url && !seen[n.url]) {
          seen[n.url] = 1;
          var fid = pf ? 'f_' + pf.replace(/\W/g, '_').slice(0, 25) : '';
          bms.push({ id: 'b' + n.id, title: n.title || n.url, url: n.url,
                     folder: fid, date: n.dateAdded || Date.now() });
        }
        if (n.children) {
          if (n.title && !skip[n.title]) {
            var folderId = 'f_' + n.title.replace(/\W/g, '_').slice(0, 25);
            var exists = false;
            for (var j = 0; j < folders.length; j++) {
              if (folders[j].id === folderId) { exists = true; break; }
            }
            if (!exists) folders.push({ id: folderId, name: n.title });
            walk(n.children, n.title);
          } else {
            walk(n.children, pf);
          }
        }
      }
    }

    walk(tree, '');
    BM = bms;
    FOLDERS = folders;
    chrome.storage.local.set({ 'ym-bm': bms, 'ym-folders': folders });
    render();
    if (!silent) toast('Synced ' + bms.length + ' bookmarks');
  });
}

function loadTabs() {
  chrome.tabs.query({}, function(tabs) {
    TABS = [];
    for (var i = 0; i < tabs.length; i++) {
      var t = tabs[i];
      TABS.push({ id: 't' + t.id, title: t.title || t.url || 'Tab',
                  url: t.url || '', date: Date.now() });
    }
    if (curView === 'tabs') render();
  });
}

// ── INIT ───────────────────────────────────────────────────────
function init() {
  buildGrid();

  // Load theme + cached bookmarks from storage first
  chrome.storage.local.get(['ym-theme', 'ym-bm', 'ym-folders'], function(r) {
    if (r['ym-theme']) applyTheme(r['ym-theme']);

    if (r['ym-bm'] && r['ym-bm'].length > 0) {
      BM = r['ym-bm'];
      FOLDERS = r['ym-folders'] || [];
      render();
    } else {
      // Nothing cached yet — auto sync on first open
      doSync(true);
    }
  });

  loadTabs();

  // ── EVENTS ──
  ge('btnSync').addEventListener('click', function(e) {
    e.stopPropagation();
    doSync(false);
  });

  ge('btnTheme').addEventListener('click', function(e) {
    e.stopPropagation();
    panelOpen = !panelOpen;
    ge('tpanel').classList.toggle('open', panelOpen);
  });

  ge('btnAdd').addEventListener('click', function(e) {
    e.stopPropagation();
    ge('m-title').value = '';
    ge('m-url').value = '';
    chrome.tabs.query({ active: true, currentWindow: true }, function(tabs) {
      if (tabs && tabs[0]) {
        ge('m-title').value = tabs[0].title || '';
        ge('m-url').value   = tabs[0].url   || '';
      }
    });
    ge('overlay').classList.add('open');
  });

  ge('btnCancel').addEventListener('click', function(e) {
    e.stopPropagation();
    ge('overlay').classList.remove('open');
  });

  ge('modal').addEventListener('click', function(e) { e.stopPropagation(); });

  ge('overlay').addEventListener('click', function() {
    ge('overlay').classList.remove('open');
  });

  ge('btnSave').addEventListener('click', function(e) {
    e.stopPropagation();
    var title = ge('m-title').value.trim();
    var url   = ge('m-url').value.trim();
    if (!title || !url) { toast('Title and URL required'); return; }
    chrome.bookmarks.create({ title: title, url: url }, function() {
      BM.unshift({ id: 'ym' + Date.now(), title: title, url: url, folder: '', date: Date.now() });
      chrome.storage.local.set({ 'ym-bm': BM, 'ym-folders': FOLDERS });
      ge('overlay').classList.remove('open');
      render();
      toast('Saved!');
    });
  });

  ge('tab-all').addEventListener('click', function(e) {
    e.stopPropagation();
    setTab('all', this);
  });
  ge('tab-recent').addEventListener('click', function(e) {
    e.stopPropagation();
    setTab('recent', this);
  });
  ge('tab-tabs').addEventListener('click', function(e) {
    e.stopPropagation();
    setTab('tabs', this);
    loadTabs();
  });

  ge('search').addEventListener('input', function() {
    curQ = this.value.trim();
    render();
  });

  ge('search').addEventListener('click', function(e) { e.stopPropagation(); });

  document.addEventListener('click', function(e) {
    if (panelOpen && !ge('tpanel').contains(e.target) && e.target !== ge('btnTheme')) {
      panelOpen = false;
      ge('tpanel').classList.remove('open');
    }
  });
}

function setTab(v, el) {
  curView = v;
  var tabs = document.querySelectorAll('.tab');
  for (var i = 0; i < tabs.length; i++) tabs[i].classList.remove('on');
  el.classList.add('on');
  render();
}

// Run after DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

})();
