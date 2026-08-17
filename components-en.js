// AINext English Shared Components
// English header/footer/cards for /en/ pages.

var headerHTML = function(backText, backHref, searchPlaceholder) {
  var link = "";
  if (backText && backHref) {
    link = '    <a href="' + backHref + '" class="back-link">← ' + backText + '</a>\n';
  }
  var search = "";
  if (searchPlaceholder) {
    search = '    <div class="header-right"><div class="search-wrap"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg><input type="text" class="search-input" id="searchInput" placeholder="' + searchPlaceholder + '" autocomplete="off" aria-label="' + searchPlaceholder + '"></div></div>\n';
  }
  return '<header class="header">\n' +
    '  <div class="header-inner">\n' +
    '    <div class="header-left">\n' +
    '      <a href="index.html" class="logo"><svg width="115" height="36" viewBox="0 0 220 68"><circle cx="32" cy="34" r="30" fill="#D45D4C"/><text x="32" y="48" text-anchor="middle" font-family="system-ui,sans-serif" font-weight="800" font-size="40" fill="#fff">AI</text><text x="68" y="48" font-family="system-ui,sans-serif" font-weight="600" font-size="40" fill="#3B2E2A">Next</text></svg></a>\n' +
    '    </div>\n' +
    link +
    search +
    '    <a href="/" class="lang-switch">中文</a>\n' +
    '  </div>\n' +
    '</header>';
};

var footerHTML = function() {
  return '<footer class="footer">\n' +
    '  <div class="container">\n' +
    '    <div class="footer-links">\n' +
    '      <a href="index.html">Home</a>\n' +
    '      <a href="about.html">About</a>\n' +
    '      <a href="privacy.html">Privacy</a>\n' +
    '      <a href="terms.html">Terms</a>\n' +
    '    </div>\n' +
    '    <p>© 2026 AINext</p>\n' +
    '  </div>\n' +
    '</footer>';
};

// ═══════════════════════════════════════════════════════════════
// Tool Card & Pagination — English version
// Uses English original fields (tagline, not tagline_zh)
// ═══════════════════════════════════════════════════════════════

var cardHTML = function(t) {
  return '<div class="tool-card" onclick="location.href=\'tools/' + t.slug + '-' + t.id + '.html\'" tabindex="0" onkeydown="if(event.key===\'Enter\')location.href=\'tools/' + t.slug + '-' + t.id + '.html\'" style="cursor:pointer">' +
    '<div class="tool-card-header">' +
      '<img src="' + t.thumbnail + '" alt="' + t.name + '" class="tool-thumb" loading="lazy" onerror="this.style.display=\'none\'">' +
      '<div class="tool-info">' +
        '<div class="tool-name">' + t.name + '</div>' +
        '<div class="tool-tagline">' + (t.tagline || '') + '</div>' +
      '</div>' +
    '</div>' +
    '<div class="tool-topics">' + (t.topics || []).slice(0, 3).map(function(tp) { return '<span class="topic-tag">' + tp.name + '</span>'; }).join('') + '</div>' +
    '<div class="tool-card-footer">' +
      '<div class="tool-stats"><span>👍 ' + (t.votesCount || 0).toLocaleString() + '</span><span>💬 ' + (t.commentsCount || 0) + '</span></div>' +
      '<a href="' + (t.website || '#') + '" target="_blank" rel="noopener" class="btn-visit" onclick="event.stopPropagation()">Visit →</a>' +
    '</div>' +
  '</div>';
};

// appendMore() — English version
var appendMore = function() {
  var cfg = window.AMC;
  var start = window.currentPage * cfg.pageSize;
  var batch = window.filteredList.slice(start, start + cfg.pageSize);
  var grid = document.getElementById(cfg.gridId);
  if (window.currentPage === 0) grid.innerHTML = '';

  if (cfg.doSort && !cfg.isSearching()) {
    window.filteredList.sort(cfg.doSort);
  }

  var html = '';
  for (var i = 0; i < batch.length; i++) {
    var globalIdx = start + i;
    if (!cfg.isSearching || !cfg.isSearching()) {
      if (globalIdx === window.nextAdAt) {
        html += (typeof window.buildNativeAdCard === 'function') ? window.buildNativeAdCard() : '';
        window.nextAdAt = globalIdx + cfg.adInterval + Math.floor(Math.random() * cfg.adRandom);
      }
    }
    html += cardHTML(batch[i]);
  }

  grid.insertAdjacentHTML('beforeend', html);
  window.currentPage++;

  var btn = document.getElementById('loadMoreBtn');
  if (btn) btn.remove();
  var loaded = window.currentPage * cfg.pageSize;
  if (loaded < window.filteredList.length) {
    grid.insertAdjacentHTML('afterend', '<button class="load-more" id="loadMoreBtn" onclick="appendMore()">Load more (' + (window.filteredList.length - loaded) + ' remaining)</button>');
  }
};
