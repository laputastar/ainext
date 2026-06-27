// [slug].js — SSR for category listing pages
// Server-renders complete HTML with embedded tool data (Googlebot-visible)

let cachedTools = null;
let cacheTime = 0;
const CACHE_TTL = 5 * 60 * 1000; // 5 min

export async function onRequest(context) {
  const { request, env } = context;
  const url = new URL(request.url);
  const slug = context.params.slug.replace(/\.html$/, '');

  // Load tools and categories
  const tools = await getTools(env, url.origin);
  const cats = await getCategories(env, url.origin);
  const cat = cats.find(c => c.id === slug);
  if (!cat) return render404(env, url.origin);

  // Filter and sort
  let ctools = tools.filter(t => t.category === slug);
  ctools.sort((a, b) => b.votesCount - a.votesCount);

  // Build slim data for embedding
  const slim = ctools.map(t => ({
    id: t.id, name: t.name, slug: t.slug,
    tagline: t.tagline || '', tagline_zh: t.tagline_zh || '',
    thumbnail: t.thumbnail, website: t.website || '',
    votesCount: t.votesCount || 0, commentsCount: t.commentsCount || 0,
    createdAt: t.createdAt || '',
    topics: (t.topics || []).map(tp => ({ name: tp.name }))
  }));

  const html = renderCategoryPage(cat, slim, url.origin);
  return new Response(html, {
    status: 200,
    headers: { 'Content-Type': 'text/html; charset=utf-8' }
  });
}

// ─── SSR HTML builder ───────────────────────────────────────────

function renderCategoryPage(cat, tools, origin) {
  const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const name = cat.name.replace(/ AI$/, '');
  const title = `AI ${name}工具 — AINext`;
  const desc = cat.description;
  const canonical = `https://www.ainext.com/category/${cat.id}.html`;

  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<base href="/">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${esc(title)}</title>
<meta name="description" content="${esc(desc)}">
<meta name="robots" content="index,follow">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<link rel="icon" type="image/svg+xml" href="ainext-icon.svg">
<link rel="apple-touch-icon" href="ainext-icon.svg">
<link rel="canonical" href="${esc(canonical)}">
<meta property="og:title" content="${esc(title)}">
<meta property="og:description" content="${esc(desc)}">
<meta property="og:image" content="https://www.ainext.com/og-image.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="${esc(title)}">
<meta name="twitter:description" content="${esc(desc)}">
<meta name="twitter:image" content="https://www.ainext.com/og-image.png">
<link rel="stylesheet" href="common.css">
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-5869913892462326" crossorigin="anonymous"></script>
<script src="ga.js"></script>
<script src="components.js"></script>
<style>
.breadcrumb{padding:16px 20px;font-size:13px;color:var(--gray-500);display:flex;align-items:center;gap:6px;max-width:1200px;margin:0 auto}
.breadcrumb a{color:var(--gray-500);text-decoration:none;transition:color .15s}
.breadcrumb a:hover{color:var(--color-primary)}
.breadcrumb span{color:var(--gray-900);font-weight:500}
.cat-header{text-align:center;padding:20px 20px 24px;max-width:800px;margin:0 auto}
.cat-header h1{font-size:28px;font-weight:800;color:var(--gray-900);margin:0 0 8px}
.cat-header p{font-size:15px;color:var(--gray-500);margin:0}
.cat-header .cat-count{display:inline-block;margin-top:12px;background:var(--gray-100);color:var(--gray-600);padding:4px 14px;border-radius:20px;font-size:13px}
.cat-tabs{display:flex;gap:4px;background:var(--gray-100);padding:4px;border-radius:12px;max-width:1200px;margin:0 auto 16px;width:fit-content}
.cat-tab{padding:8px 20px;border-radius:10px;font-size:14px;font-weight:500;color:var(--gray-500);transition:all .15s;white-space:nowrap;background:none;border:none;cursor:pointer;font-family:inherit}
.cat-tab:hover{color:var(--gray-700)}
.cat-tab.active{background:#fff;color:var(--gray-900);box-shadow:0 1px 3px rgba(0,0,0,.08);font-weight:600}
.tool-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px;max-width:1200px;margin:0 auto;padding:0 20px 24px}
.tool-card{background:#fff;border:1px solid var(--color-border);border-radius:10px;padding:20px;cursor:pointer;transition:box-shadow .2s,transform .2s}
.tool-card:hover{box-shadow:0 4px 16px rgba(0,0,0,.08);transform:translateY(-2px)}
.tool-card-header{display:flex;align-items:flex-start;gap:12px}
.tool-thumb{width:48px;height:48px;border-radius:8px;object-fit:cover;flex-shrink:0}
.tool-info{flex:1;min-width:0}
.tool-name{font-size:16px;font-weight:700;color:var(--gray-900);margin-bottom:4px}
.tool-tagline{font-size:13px;color:var(--gray-500);line-height:1.4;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.tool-topics{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0}
.topic-tag{background:var(--gray-100);color:var(--gray-600);padding:2px 10px;border-radius:6px;font-size:11px;font-weight:500}
.tool-card-footer{display:flex;align-items:center;justify-content:space-between;margin-top:12px;padding-top:12px;border-top:1px solid var(--color-border)}
.tool-stats{display:flex;gap:14px;font-size:12px;color:var(--gray-400)}
.btn-visit{font-size:12px;font-weight:600;color:var(--color-primary);text-decoration:none;transition:opacity .15s}
.btn-visit:hover{opacity:.8}
.load-more{display:block;width:100%;max-width:1200px;margin:0 auto 48px;padding:14px;border:1.5px dashed var(--color-border);border-radius:12px;background:0;color:var(--gray-500);font-size:15px;font-weight:600;cursor:pointer;transition:all .15s;font-family:inherit}
.load-more:hover{background:var(--gray-50);color:var(--gray-700)}
.cat-back{text-align:center;padding:0 20px 48px}
.cat-back a{color:var(--color-primary);text-decoration:none;font-size:14px;font-weight:500}
@media(max-width:768px){.tool-grid{grid-template-columns:repeat(2,1fr)}}
@media(max-width:640px){.tool-grid{grid-template-columns:1fr}.cat-tabs{width:calc(100% - 40px)}.cat-tab{flex:1;text-align:center}}
</style>
</head>
<body>
<script>document.write(headerHTML('','','搜索${esc(name)}工具...'))</script>
<div class="breadcrumb"><a href="index.html">首页</a><span>/</span><span>${esc(name)}</span></div>
<div class="cat-header">
  <h1>AI ${esc(name)}工具</h1>
  <p>${esc(desc)}</p>
  <div class="cat-count">共 ${tools.length} 款工具</div>
</div>
<div class="cat-tabs">
  <button class="cat-tab active" data-sort="hot">🔥 热度</button>
  <button class="cat-tab" data-sort="latest">🕐 最新</button>
</div>
<div class="tool-grid" id="toolGrid"></div>
<div class="cat-back"><a href="index.html">← 回到首页浏览全部工具</a></div>
<script>document.write(footerHTML())</script>
<script src="ad.js"></script>
<script>
(function(){
var tools = ${JSON.stringify(tools)};
var CAT_COUNT = tools.length;
var PAGE_SIZE = 24;
var currentPage = 0;
var filteredList = tools.slice();
var searchQuery = '';
var sortMode = 'hot';

function cardHTML(t){
  var nm = t.name.replace(/&/g,'&amp;').replace(/</g,'&lt;');
  var tl = (t.tagline_zh || t.tagline).replace(/&/g,'&amp;').replace(/</g,'&lt;');
  var tpc = (t.topics||[]).slice(0,3).map(function(tp){return '<span class="topic-tag">'+tp.name+'</span>';}).join('');
  return '<div class="tool-card" onclick="location.href=\\'tools/'+t.slug+'-'+t.id+'.html\\'" tabindex="0" onkeydown="if(event.key===\\'Enter\\')location.href=\\'tools/'+t.slug+'-'+t.id+'.html\\'" style="cursor:pointer"><div class="tool-card-header"><img src="'+t.thumbnail+'" alt="'+nm+'" class="tool-thumb" loading="lazy" onerror="this.style.display=\\'none\\'"><div class="tool-info"><div class="tool-name">'+nm+'</div><div class="tool-tagline">'+tl+'</div></div></div><div class="tool-topics">'+tpc+'</div><div class="tool-card-footer"><div class="tool-stats"><span>👍 '+(t.votesCount||0).toLocaleString()+'</span><span>💬 '+(t.commentsCount||0)+'</span></div><a href="'+(t.website||'#')+'" target="_blank" rel="noopener" class="btn-visit" onclick="event.stopPropagation()">访问官网 →</a></div></div>';
}

var nextAdAt = 8 + Math.floor(Math.random() * 3); // shared across appendMore calls

function appendMore(){
  if (!searchQuery) {
    if (sortMode === 'latest') {
      filteredList.sort(function(a,b){ return new Date(b.createdAt) - new Date(a.createdAt); });
    } else {
      filteredList.sort(function(a,b){ return b.votesCount - a.votesCount; });
    }
  }
  var start = currentPage * PAGE_SIZE;
  var batch = filteredList.slice(start, start + PAGE_SIZE);
  var grid = document.getElementById('toolGrid');
  if (currentPage === 0) grid.innerHTML = '';

  var html = '';
  for (var i = 0; i < batch.length; i++){
    var globalIdx = start + i;
    if (globalIdx === nextAdAt && !searchQuery){
      html += (typeof window.buildNativeAdCard === 'function') ? window.buildNativeAdCard() : '';
      nextAdAt = globalIdx + 8 + Math.floor(Math.random() * 3);
    }
    html += cardHTML(batch[i]);
  }

  grid.insertAdjacentHTML('beforeend', html);
  currentPage++;

  var btn = document.getElementById('loadMoreBtn');
  if (btn) btn.remove();
  if (currentPage * PAGE_SIZE < filteredList.length){
    var remain = filteredList.length - currentPage * PAGE_SIZE;
    grid.insertAdjacentHTML('afterend', '<button class="load-more" id="loadMoreBtn" onclick="appendMore()">加载更多 ('+remain+' 个剩余)</button>');
  }
}

document.querySelectorAll('.cat-tab').forEach(function(tab){
  tab.addEventListener('click', function(){
    document.querySelectorAll('.cat-tab').forEach(function(t){ t.classList.remove('active'); });
    this.classList.add('active');
    sortMode = this.dataset.sort;
    currentPage = 0;
    filteredList = searchQuery ? tools.filter(function(t){ return (t.name+' '+(t.tagline_zh||t.tagline||'')).toLowerCase().indexOf(searchQuery) >= 0; }) : tools.slice();
    appendMore();
  });
});

var searchInput = document.querySelector('.header-right .search-input');
if (searchInput) {
  searchInput.addEventListener('input', function(){
    var q = this.value.toLowerCase();
    searchQuery = q;
    if (!q) {
      filteredList = tools.slice();
      document.querySelector('.cat-count').textContent = '共 ' + CAT_COUNT + ' 款工具';
    } else {
      filteredList = tools.filter(function(t){
        return (t.name + ' ' + (t.tagline_zh||t.tagline||'')).toLowerCase().indexOf(q) >= 0;
      });
      document.querySelector('.cat-count').textContent = '共 ' + filteredList.length + ' / ' + CAT_COUNT + ' 款工具';
    }
    currentPage = 0;
    appendMore();
    document.querySelector('.cat-count').scrollIntoView({behavior:'smooth',block:'start'});
  });
}

appendMore();
window.appendMore = appendMore;
})();
</script>
</body>
</html>`;
}

// ─── Utils ────────────────────────────────────────────────────────

async function getTools(env, origin) {
  const now = Date.now();
  if (cachedTools && now - cacheTime < CACHE_TTL) return cachedTools;
  const res = await env.ASSETS.fetch(new Request(`${origin}/tools.json`));
  if (!res.ok) throw new Error('Failed to load tools.json');
  cachedTools = await res.json();
  cacheTime = now;
  return cachedTools;
}

async function getCategories(env, origin) {
  const res = await env.ASSETS.fetch(new Request(`${origin}/categories.json`));
  if (!res.ok) throw new Error('Failed to load categories.json');
  const data = await res.json();
  return data.categories || data;
}

async function render404(env, origin) {
  const nf = await env.ASSETS.fetch(new Request(`${origin}/404.html`));
  return new Response(await nf.text(), {
    status: 404,
    headers: { 'Content-Type': 'text/html; charset=utf-8' }
  });
}
