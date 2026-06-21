// AINext Shared Components
// Header and Footer for all pages. Change once, update everywhere.

var headerHTML = function(backText, backHref) {
  var link = "";
  if (backText && backHref) {
    link = '    <a href="' + backHref + '" class="back-link">← ' + backText + '</a>\n';
  }
  return '<header class="header">\n' +
    '  <div class="header-inner">\n' +
    '    <div class="header-left">\n' +
    '      <a href="index.html" class="logo"><svg width="115" height="27" viewBox="0 0 230 54"><circle cx="26" cy="27" r="25" fill="#D45D4C"/><text x="26" y="37" text-anchor="middle" font-family="system-ui,sans-serif" font-weight="800" font-size="30" fill="#fff">AI</text><text x="54" y="37" font-family="system-ui,sans-serif" font-weight="600" font-size="30" fill="#3B2E2A">Next</text></svg></a>\n' +
    '    </div>\n' +
    link +
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
