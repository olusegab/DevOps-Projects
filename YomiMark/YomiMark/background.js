var windowId = null;

// Open/focus the main window instead of a popup
chrome.action.onClicked.addListener(function() {
  if (windowId !== null) {
    chrome.windows.get(windowId, function(win) {
      if (chrome.runtime.lastError || !win) {
        windowId = null;
        openWindow();
      } else {
        chrome.windows.update(windowId, { focused: true });
      }
    });
  } else {
    openWindow();
  }
});

function openWindow() {
  chrome.windows.create({
    url: chrome.runtime.getURL('app.html'),
    type: 'popup',
    width: 480,
    height: 680,
    focused: true
  }, function(win) {
    windowId = win.id;
  });
}

chrome.windows.onRemoved.addListener(function(id) {
  if (id === windowId) windowId = null;
});

// Sync bookmarks
function doSync(cb) {
  chrome.bookmarks.getTree(function(tree) {
    if (chrome.runtime.lastError || !tree) { if (cb) cb(0); return; }
    var bms = [], folders = [], seen = {};
    var skip = { '':1,'Bookmarks bar':1,'Other bookmarks':1,'Mobile bookmarks':1,
                 'Bookmarks Bar':1,'Favorites bar':1,'Bookmarks':1,'Other':1 };
    function walk(nodes, pf) {
      for (var i = 0; i < nodes.length; i++) {
        var n = nodes[i];
        if (n.url && !seen[n.url]) {
          seen[n.url] = 1;
          bms.push({ id:'b'+n.id, title:n.title||n.url, url:n.url,
                     folder: pf ? 'f_'+pf.replace(/\W/g,'_').slice(0,25) : '',
                     date: n.dateAdded || Date.now() });
        }
        if (n.children) {
          if (n.title && !skip[n.title]) {
            var fid = 'f_'+n.title.replace(/\W/g,'_').slice(0,25);
            if (!folders.find(function(f){return f.id===fid;}))
              folders.push({ id:fid, name:n.title });
            walk(n.children, n.title);
          } else walk(n.children, pf);
        }
      }
    }
    walk(tree, '');
    chrome.storage.local.set({ 'ym-bm':bms, 'ym-folders':folders, 'ym-synced':Date.now() });
    if (cb) cb(bms.length);
  });
}

chrome.runtime.onInstalled.addListener(function() { doSync(); });
chrome.runtime.onStartup.addListener(function() { doSync(); });
chrome.bookmarks.onCreated.addListener(function() { doSync(); });
chrome.bookmarks.onRemoved.addListener(function() { doSync(); });
chrome.bookmarks.onChanged.addListener(function() { doSync(); });

chrome.runtime.onMessage.addListener(function(msg, sender, sendResponse) {
  if (msg === 'sync') { doSync(function(n){ sendResponse(n); }); return true; }
  if (msg === 'ping') { sendResponse('pong'); return false; }
});
