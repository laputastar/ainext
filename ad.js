// AINext Ad Component
// 统一管理全站 6 个广告位。上线后填入 AdSense 代码即可
// 当前未配置时，保持原有占位样式不变

const AD_CONFIG = {
  enabled: false,  // 上线后改为 true
  slots: {
    // 首页 Banner ×2（Hero 下方 + 工具列表中间）
    '.ad-slot-responsive': '',  // 填入 <ins class="adsbygoogle"...>
    
    // 详情页 Banner ×2（评论上方 + 相关推荐上方）
    '.ad-box': '',
    
    // 首页原生信息流 ×2（工具列表第5位 + 第13位）
    '.tool-card-ad': '',
  }
};

(function initAds(){
  if(!AD_CONFIG.enabled) return;
  
  Object.entries(AD_CONFIG.slots).forEach(([selector,code]) => {
    if(!code) return;
    document.querySelectorAll(selector).forEach(el => {
      el.innerHTML = code;
    });
  });
})();
