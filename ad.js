// AINext Unified Ad Component
// 全站广告位统一管理：占位符渲染 + AdSense 代码注入 + 原生广告卡
// 上线后只需改下面 3 处：enabled、slots 里的 code、nativeAdCode

const AD_CONFIG = {
  enabled: false,  // 上线后改为 true

  // 固定广告位：selector = 页面中的容器，placeholder = 未启用时的占位文字，code = AdSense 代码
  slots: [
    { selector: '.ad-slot-index-top',    placeholder: '广告位招租 (响应式)', code: '' },
    { selector: '.ad-slot-index-mid',    placeholder: '广告位招租 (响应式)', code: '' },
    { selector: '.ad-slot-detail-top',   placeholder: '广告位 (详情页)',     code: '' },
    { selector: '.ad-slot-detail-bottom',placeholder: '广告位 (详情页)',     code: '' },
  ],

  // 流内原生广告：每 N 张工具卡之间插入一张广告卡
  nativeAdInterval: 7,
  nativeAdTemplate: '' // 填入 <ins class="adsbygoogle" data-ad-format="fluid" ...></ins>
};

(function initAds() {
  // 1. 固定广告位渲染
  AD_CONFIG.slots.forEach(function(s) {
    var els = document.querySelectorAll(s.selector);
    els.forEach(function(el) {
      if (AD_CONFIG.enabled && s.code) {
        el.innerHTML = s.code;
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
})();
