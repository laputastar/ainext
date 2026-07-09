// [slug].js — SSR for tool detail pages
// Server-renders complete HTML with SEO content (Googlebot-visible)
import { getTools, render404 } from '../_shared.js';

const CAT_CN = {
  'ai-tool': '', chatbot: '对话', coding: '编程',
  education: '教育', finance: '金融', health: '健康',
  image: '图像', marketing: '营销', productivity: '效率',
  video: '视频', writing: '写作',
};

export async function onRequest(context) {
  const { request, env } = context;
  const url = new URL(request.url);
  const slug = context.params.slug;

  // Extract tool ID from URL (e.g. "goldfish-1153772" or "goldfish-1153772.html")
  const idMatch = slug.match(/(\d+)(?:\.html)?$/);
  if (!idMatch) return render404(env, url.origin);

  const toolId = idMatch[1];

  // Load tools.json
  const tools = await getTools(env, url.origin);
  const tool = tools.find(t => String(t.id) === toolId);
  if (!tool) return render404(env, url.origin);

  // Build SSR HTML
  const html = renderToolPage(tool, tools, url.origin);
  return new Response(html, {
    status: 200,
    headers: {
      'Content-Type': 'text/html; charset=utf-8',
      'X-Frame-Options': 'SAMEORIGIN',
      'X-Content-Type-Options': 'nosniff',
      'Referrer-Policy': 'strict-origin-when-cross-origin'
    }
  });
}

function buildSEOTitle(tool) {
  const taglineFull = tool.tagline_zh || tool.tagline || '';
  const suffix = ' | AINext';
  if (!taglineFull) return `${tool.name} | AINext`;
  const sep = ' - ';
  const full = `${tool.name}${sep}${taglineFull}${suffix}`;
  if (full.length <= 60) return full;
  const maxTagline = 60 - tool.name.length - sep.length - suffix.length;
  if (maxTagline > 0) return `${tool.name}${sep}${taglineFull.slice(0, maxTagline)}${suffix}`;
  return tool.name.slice(0, 60 - suffix.length) + suffix;
}

// ─── SSR HTML builder ───────────────────────────────────────────

function renderToolPage(tool, allTools, origin) {
  const toolUrl = `tools/${tool.slug}-${tool.id}.html`;
  const title = buildSEOTitle(tool);
  const tagline = tool.tagline_zh || tool.tagline || '';
  const desc = (tool.description_zh || tool.description || '').replace(/\n/g, '<br>');
  const catCN = CAT_CN[tool.category] || '';
  const catLabel = catCN ? `AI${catCN}工具` : 'AI工具';
  const shortDesc = (tool.description_zh || tool.description || tagline || '').replace(/\n/g, ' ').slice(0, 120);
  const metaDesc = `${tool.name} 是一款 ${catLabel}。${shortDesc} - AINext 精选`;
  const thumb = tool.thumbnail || '';
  const dateStr = new Date(tool.createdAt).toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' });
  const topics = tool.topics || [];
  const mediaImages = (tool.media || []).filter(m => m.type === 'image' && m.url);
  const canonicalUrl = `https://www.ainext.com/${toolUrl}`;

  // Related tools (same category, same for everyone viewing this page)
  const related = allTools
    .filter(t => t.category === tool.category && t.id !== tool.id)
    .sort((a, b) => b.votesCount - a.votesCount)
    .slice(0, 6);

  // Escape helper
  const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<base href="/">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${esc(title)}</title>
<meta name="description" content="${esc(metaDesc)}">
<meta name="robots" content="index,follow">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<link rel="icon" type="image/svg+xml" href="ainext-icon.svg">
<link rel="apple-touch-icon" href="ainext-icon.svg">
<link rel="canonical" href="${esc(canonicalUrl)}">
<meta property="og:title" content="${esc(title)}">
<meta property="og:description" content="${esc(metaDesc)}">
<meta property="og:image" content="${mediaImages.length ? esc(mediaImages[0].url) : 'https://www.ainext.com/og-image.png'}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:url" content="${esc(canonicalUrl)}">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="${esc(title)}">
<meta name="twitter:description" content="${esc(metaDesc)}">
<meta name="twitter:image" content="${mediaImages.length ? esc(mediaImages[0].url) : 'https://www.ainext.com/og-image.png'}">
<script type="application/ld+json">${JSON.stringify({"@context":"https://schema.org","@type":"WebPage","name":tool.name,"url":canonicalUrl})}</script>
<script type="application/ld+json">${JSON.stringify({"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[{"@type":"ListItem","position":1,"name":"AINext","item":"https://www.ainext.com/"},{"@type":"ListItem","position":2,"name":tool.name,"item":canonicalUrl}]})}</script>
<script type="application/ld+json">${JSON.stringify({"@context":"https://schema.org","@type":"SoftwareApplication","name":tool.name,"description":metaDesc,"operatingSystem":"Web","applicationCategory":tool.category||"AI"})}</script>
<link rel="stylesheet" href="common.css">
<style>
.container{max-width:960px}
.detail-hero{background:#fff;border:1px solid var(--color-border);border-radius:var(--radius-card);overflow:hidden;box-shadow:0 1px 2px rgba(0,0,0,.03);margin-top:20px}
.detail-hero-top{display:flex;align-items:flex-start;gap:16px;padding:20px 24px 16px}
.detail-hero-thumb{width:56px;height:56px;border-radius:12px;object-fit:cover;background:var(--gray-100);flex-shrink:0;box-shadow:var(--shadow-sm)}
.detail-hero-info{flex:1;min-width:0;display:flex;flex-direction:column;justify-content:center}
.detail-hero-name{font-size:26px;font-weight:800;color:var(--gray-900);line-height:1.2;letter-spacing:-0.015em}
.detail-hero-tagline{font-size:14px;color:var(--gray-500);margin-top:3px;line-height:1.4}
.detail-hero-actions{display:flex;gap:8px;flex-shrink:0;align-self:center}
.detail-hero-desc{padding:0 24px 0;font-size:14px;color:var(--gray-700);line-height:1.7}
.detail-hero-desc p:first-child{font-size:15px;font-weight:500;color:var(--gray-900)}
.detail-hero-topics{display:flex;gap:6px;flex-wrap:wrap;padding:12px 24px 16px}
.topic-pill{padding:5px 12px;border-radius:20px;font-size:12px;font-weight:500;background:var(--gray-100);color:var(--gray-700)}
.detail-hero-gallery{position:relative;background:var(--gray-100);aspect-ratio:16/9;display:flex;align-items:center;justify-content:center;border-top:1px solid var(--color-border-light);margin-top:8px}
.detail-hero-gallery img{width:100%;height:100%;object-fit:contain}
.detail-hero-gallery .gallery-placeholder{color:var(--gray-400);font-size:14px}
.detail-meta-bar{display:flex;align-items:center;gap:20px;padding:8px 4px 14px;font-size:13px;color:var(--gray-400)}
.detail-meta-bar span{display:flex;align-items:center;gap:4px}
.btn-primary{padding:10px 22px;border-radius:var(--radius-btn);background:var(--color-primary);color:#fff;font-size:14px;font-weight:600;display:inline-flex;align-items:center;gap:6px;transition:all .15s;white-space:nowrap}
.btn-primary:hover{background:var(--color-primary-hover);box-shadow:0 4px 12px rgba(180,83,9,.25)}
.btn-outline{padding:10px 22px;border-radius:var(--radius-btn);background:#fff;border:1.5px solid var(--color-border);color:var(--gray-700);font-size:14px;font-weight:500;display:inline-flex;align-items:center;gap:6px;transition:all .15s;white-space:nowrap}
.btn-outline:hover{background:var(--gray-100);border-color:var(--gray-300)}
.gallery-nav{position:absolute;top:50%;transform:translateY(-50%);width:40px;height:40px;border-radius:50%;background:rgba(255,255,255,.85);box-shadow:var(--shadow-sm);display:flex;align-items:center;justify-content:center;color:var(--gray-700);transition:all .15s;z-index:2}
.gallery-nav:hover{background:#fff;box-shadow:var(--shadow-md)}
.gallery-nav.prev{left:12px}.gallery-nav.next{right:12px}
.gallery-nav svg{width:18px;height:18px}
.gallery-thumbs{display:flex;gap:8px;margin:0;padding:8px 24px 14px;overflow-x:auto}
.gallery-thumb{width:80px;height:52px;border-radius:6px;overflow:hidden;border:2px solid transparent;cursor:pointer;flex-shrink:0;transition:all .15s;background:var(--gray-100)}
.gallery-thumb:hover{border-color:var(--gray-300)}
.gallery-thumb.active{border-color:var(--color-primary)}
.gallery-thumb img{width:100%;height:100%;object-fit:cover}
.section{margin-bottom:32px}
.section-title{font-size:18px;font-weight:700;color:var(--gray-900);margin-bottom:12px;display:flex;align-items:center;gap:6px}
.info-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px 28px;background:#fff;border:1px solid var(--color-border);border-radius:var(--radius-card);padding:20px 24px;box-shadow:0 1px 2px rgba(0,0,0,.03)}
.info-item{font-size:14px}.info-label{color:var(--gray-400);margin-bottom:3px}.info-value{color:var(--gray-700);font-weight:500}
.comments-box{background:#fff;border:1px solid var(--color-border);border-radius:var(--radius-card);padding:20px 24px;box-shadow:0 1px 2px rgba(0,0,0,.03)}
.comments-box p{font-size:14px;color:var(--gray-500);margin-bottom:10px}
.comments-link{display:inline-flex;align-items:center;gap:6px;color:var(--color-primary);font-weight:600;font-size:14px}
.comments-link:hover{color:var(--color-primary-dark)}
.related-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;padding-bottom:64px}
.related-card{background:#fff;border:1px solid var(--color-border);border-radius:var(--radius-card);padding:14px;box-shadow:0 1px 2px rgba(0,0,0,.03);transition:all .2s;text-decoration:none;display:block}
.related-card:hover{border-color:var(--gray-300);box-shadow:var(--shadow-sm);transform:translateY(-1px)}
.related-top{display:flex;align-items:center;gap:10px;margin-bottom:6px}
.related-img{width:40px;height:40px;border-radius:8px;object-fit:cover;background:var(--gray-100)}
.related-name{font-size:14px;font-weight:600;color:var(--gray-900);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.related-tagline{font-size:12px;color:var(--gray-500);line-height:1.4;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.related-stats{display:flex;gap:10px;font-size:12px;color:var(--gray-400);margin-top:6px}
.state-box{text-align:center;padding:80px 20px}
.state-box h2{font-size:18px;font-weight:600;color:var(--gray-900);margin-bottom:8px}
.state-box p{font-size:14px;color:var(--gray-500)}
.spinner{width:28px;height:28px;border:3px solid var(--gray-200);border-top-color:var(--color-primary);border-radius:50%;animation:spin .8s linear infinite;margin:0 auto 10px}
@keyframes spin{to{transform:rotate(360deg)}}
.footer p{font-size:12px;color:var(--gray-400)}
@media(max-width:768px){
  .detail-hero-name{font-size:22px}.detail-hero-thumb{width:48px;height:48px;border-radius:10px}
  .detail-hero-top{padding:16px 16px 12px;gap:12px}
  .detail-hero-actions{flex-direction:column;align-self:stretch}
  .detail-hero-actions .btn-primary,.detail-hero-actions .btn-outline{justify-content:center}
  .info-grid{grid-template-columns:1fr}.related-grid{grid-template-columns:1fr}
  .gallery-thumb{width:64px;height:40px}.gallery-thumbs{padding:6px 16px 10px}
}
@media(max-width:640px){
  .detail-hero-name{font-size:20px}
  .detail-hero-top{flex-wrap:wrap;padding:14px 14px 10px}
  .detail-hero-actions{flex-direction:row;width:100%;margin-top:4px}
  .gallery-nav{width:32px;height:32px}
  .gallery-thumb{width:56px;height:34px}
}
</style>
<script src="ga.js"></script>
<script src="components.js"></script>
</head>
<body>

<script>document.write(headerHTML('返回列表','index.html'))</script>

<main>
  <div class="container" style="max-width:960px">
    <div class="detail-hero">
      <div class="detail-hero-top">
        ${thumb ? `<img src="${esc(thumb)}" alt="${esc(tool.name)}" class="detail-hero-thumb" onerror="this.style.display='none'">` : ''}
        <div class="detail-hero-info">
          <h1 class="detail-hero-name">${esc(tool.name)}</h1>
          <div class="detail-hero-tagline">${esc(tagline)}</div>
        </div>
        <div class="detail-hero-actions">
          <a href="${esc(tool.website || '#')}" target="_blank" rel="noopener" class="btn-primary">🌐 访问官网</a>
          ${tool.ph_url ? `<a href="${esc(tool.ph_url)}" target="_blank" rel="noopener" class="btn-outline">🚀 PH</a>` : ''}
        </div>
      </div>
      <div class="detail-hero-desc">
        ${desc ? `<p style="font-size:15px;font-weight:500;color:var(--gray-900);margin-bottom:8px">${desc}</p>` : '<p>暂无更多描述</p>'}
      </div>
      ${topics.length ? `
        <div class="detail-hero-topics">
          ${topics.map(t => `<span class="topic-pill">${esc(t.name)}</span>`).join('')}
        </div>
      ` : ''}
      ${mediaImages.length ? `
        <div class="detail-hero-gallery" id="galleryMain">
          <img src="${esc(mediaImages[0].url)}" alt="${esc(tool.name)} 截图" id="galleryMainImg" onerror="this.style.display='none';document.getElementById('galleryFallback').style.display='flex'">
          <div class="gallery-placeholder" id="galleryFallback" style="display:none">📸 ${esc(tool.name)}</div>
          ${mediaImages.length > 1 ? `
            <button class="gallery-nav prev" onclick="navigateGallery(-1)" aria-label="上一张截图"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="m15 18-6-6 6-6"/></svg></button>
            <button class="gallery-nav next" onclick="navigateGallery(1)" aria-label="下一张截图"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="m9 18 6-6-6-6"/></svg></button>
          ` : ''}
        </div>
        ${mediaImages.length > 1 ? `
          <div class="gallery-thumbs" id="galleryThumbs">
            ${mediaImages.map((m, i) => `<div class="gallery-thumb${i === 0 ? ' active' : ''}" onclick="setGalleryImage(${i})"><img src="${esc(m.url)}" alt="${esc(tool.name)} 截图 ${i + 1}" loading="lazy" onerror="this.style.display='none'"></div>`).join('')}
          </div>
        ` : ''}
      ` : ''}
    </div>
    <div class="detail-meta-bar" id="metaBar">
      <span>👍 ${tool.votesCount.toLocaleString()}</span>
      <span>💬 ${tool.commentsCount} 评论</span>
      <span>🕐 ${dateStr}</span>
    </div>

    <div class="ad-slot ad-slot-detail-top"><div class="ad-placeholder">广告位 (响应式横幅)</div></div>

    <section class="section">
      <h2 class="section-title">💬 用户评论</h2>
      <div class="comments-box">
        <p>该工具在 Product Hunt 上有 <strong>${tool.commentsCount}</strong> 条评论。</p>
        ${tool.ph_url ? `<a href="${esc(tool.ph_url)}" target="_blank" rel="noopener" class="comments-link">在 Product Hunt 上查看评论 →</a>` : ''}
      </div>
    </section>

    <section class="section">
      <h2 class="section-title">📋 基本信息</h2>
      <div class="info-grid">
        <div class="info-item"><div class="info-label">上线日期</div><div class="info-value">${dateStr}</div></div>
        <div class="info-item"><div class="info-label">点赞数</div><div class="info-value">${tool.votesCount.toLocaleString()}</div></div>
        <div class="info-item"><div class="info-label">评论数</div><div class="info-value">${tool.commentsCount}</div></div>
        <div class="info-item"><div class="info-label">数据来源</div><div class="info-value">网络公开数据</div></div>
      </div>
    </section>

    <div class="ad-slot ad-slot-detail-bottom"><div class="ad-placeholder">广告位 (响应式横幅)</div></div>

    ${related.length ? `<section class="section"><h2 class="section-title">🔗 相关推荐</h2><div class="related-grid">${related.map(r => `<a href="tools/${esc(r.slug)}-${esc(r.id)}.html" class="related-card"><div class="related-top"><img src="${esc(r.thumbnail || '')}" alt="${esc(r.name)}" class="related-img" loading="lazy" onerror="this.style.display='none'"><div class="related-name">${esc(r.name)}</div></div><div class="related-tagline">${esc(r.tagline_zh || r.tagline)}</div><div class="related-stats"><span>👍 ${r.votesCount.toLocaleString()}</span><span>💬 ${r.commentsCount}</span></div></a>`).join('')}</div></section>` : ''}
  </div>
</main>

<script>document.write(footerHTML())</script>

<script>
// Gallery JS
${mediaImages.length > 1 ? `
(function(){
  var gImgs = ${JSON.stringify(mediaImages.map(m => m.url))};
  var gIdx = 0;
  window.setGalleryImage = function(i){
    gIdx = i;
    var img = document.getElementById('galleryMainImg');
    if(img) img.src = gImgs[i];
    document.querySelectorAll('.gallery-thumb').forEach(function(t,j){ t.classList.toggle('active', j===i); });
  };
  window.navigateGallery = function(dir){
    gIdx = (gIdx + dir + gImgs.length) % gImgs.length;
    setGalleryImage(gIdx);
  };
})();
` : ''}

// Refresh dynamic stats (votes/comments) from latest tools.json
(function(){
  fetch('/tools.json').then(function(r){ return r.json(); }).then(function(all){
    var t = all.find(function(x){ return String(x.id) === '${tool.id}'; });
    if(!t) return;
    var bar = document.getElementById('metaBar');
    if(bar) bar.innerHTML = '<span>👍 ' + t.votesCount.toLocaleString() + '</span><span>💬 ' + t.commentsCount + ' 评论</span><span>🕐 ${dateStr}</span>';
  }).catch(function(){});
})();
</script>
<script src="ad.js"></script>
</body>
</html>`;
}
