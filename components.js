// AINext Shared Components
// Header and Footer for all pages. Change once, update everywhere.

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
    '  </div>\n' +
    '</header>';
};

var footerHTML = function() {
  return '<footer class="footer">\n' +
    '  <div class="container">\n' +
    '    <div class="footer-links">\n' +
    '      <a href="index.html">首页</a>\n' +
    '      <a href="about.html">关于我们</a>\n' +
    '      <a href="privacy.html">隐私政策</a>\n' +
    '      <a href="terms.html">服务条款</a>\n' +
    '    </div>\n' +
    '    <p>© 2026 AINext</p>\n' +
    '  </div>\n' +
    '</footer>';
};
