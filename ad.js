// AINext Unified Ad Component
// 全站广告位统一管理：占位符渲染 + AdSense 代码注入 + 原生广告卡
// 上线后只需改下面 3 处：enabled、slots 里的 code、nativeAdCode

const AD_CONFIG = {
  enabled: false,  // 上线后改为 true

  // 共享横幅代码（4 个固定位共用）
  bannerCode: '<ins class="adsbygoogle" style="display:block" data-ad-client="ca-pub-5869913892462326" data-ad-slot="1084779702" data-ad-format="auto" data-full-width-responsive="true"></ins><script>(adsbygoogle = window.adsbygoogle || []).push({});<\/script>',

  // 固定广告位：selector = 页面中的容器，placeholder = 未启用时的占位文字
  slots: [
    { selector: '.ad-slot-index-top',    placeholder: '广告位招租 (响应式)' },
    { selector: '.ad-slot-index-mid',    placeholder: '广告位招租 (响应式)' },
    { selector: '.ad-slot-detail-top',   placeholder: '广告位 (详情页)'     },
    { selector: '.ad-slot-detail-bottom',placeholder: '广告位 (详情页)'     },
  ],

  // 流内原生广告：每 N 张工具卡之间插入一张广告卡
  nativeAdInterval: 7,
  nativeAdTemplate: '<ins class="adsbygoogle" style="display:block" data-ad-format="fluid" data-ad-layout-key="-gv-a+42-7z+2l" data-ad-client="ca-pub-5869913892462326" data-ad-slot="6229295175"></ins>'
};

(function initAds() {
  // 0. 动态加载 AdSense SDK（全局一份，不碰页面文件）
  if (AD_CONFIG.enabled) {
    var s = document.createElement('script');
    s.async = true;
    s.src = 'https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-5869913892462326';
    s.crossOrigin = 'anonymous';
    document.head.appendChild(s);
  }

  // 1. 固定广告位渲染
  AD_CONFIG.slots.forEach(function(s) {
    var els = document.querySelectorAll(s.selector);
    els.forEach(function(el) {
      if (AD_CONFIG.enabled && AD_CONFIG.bannerCode) {
        el.innerHTML = AD_CONFIG.bannerCode;
      } else {
        el.innerHTML = '<div class="ad-placeholder">' + s.placeholder + '</div>';
      }
    });
  });

  // 2. 暴露广告卡 HTML 构建器（供 renderGrid 调用）
  window.buildNativeAdCard = function() {
    if (!AD_CONFIG.enabled || !AD_CONFIG.nativeAdTemplate) {
      return '<div class="tool-card tool-card-ad"><div class="ad-placeholder">原生广告位</div></div>';
    }
    return '<div class="tool-card tool-card-ad">' + AD_CONFIG.nativeAdTemplate + '</div>';
  };

  // 3. 暴露投放间隔
  window.getAdInterval = function() {
    return AD_CONFIG.nativeAdInterval;
  };

  // 4. 暴露是否启用
  window.isAdEnabled = function() {
    return AD_CONFIG.enabled;
  };

  // 5. 自动检测原生广告卡的 DOM 插入并刷新（不碰任何页面文件）
  var gridEl = document.getElementById('toolGrid');
  if (gridEl) {
    var observer = new MutationObserver(function(mutations) {
      mutations.forEach(function(m) {
        m.addedNodes.forEach(function(node) {
          if (node.nodeType === 1 && (node.classList.contains('tool-card-ad') || node.querySelector('.tool-card-ad'))) {
            try { (window.adsbygoogle || []).push({}); } catch(e) {}
            observer.disconnect(); // 每次 push 后断开，等待下次 insertAdjacentHTML
            if (gridEl) observer.observe(gridEl, { childList: true, subtree: true });
          }
        });
      });
    });
    observer.observe(gridEl, { childList: true, subtree: true });
  }
})();
