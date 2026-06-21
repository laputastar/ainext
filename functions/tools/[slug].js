// functions/tools/[slug].js
// 处理 /tools/* 路由：存在工具 → 200，不存在 → 真实 404

export async function onRequest(context) {
  const { request, env } = context;
  const url = new URL(request.url);
  const slug = context.params.slug;

  // 1. 读取 tools.json（带缓存）
  const tools = await getTools(env, url.origin);

  // 2. 提取工具 ID
  const idMatch = slug.match(/(\d+)\.html$/);
  if (!idMatch) {
    return render404(env, url.origin);
  }

  const tool = tools.find(t => String(t.id) === idMatch[1]);

  // 3. 不存在 → 404
  if (!tool) {
    return render404(env, url.origin);
  }

  // 4. 存在 → 返回 detail.html（已有 <base href="/">，无需注入）
  const detailRes = await env.ASSETS.fetch(
    new Request(`${url.origin}/detail.html`)
  );

  return new Response(await detailRes.text(), {
    status: 200,
    headers: { 'Content-Type': 'text/html; charset=utf-8' }
  });
}

// 缓存 wrapper
let cachedTools = null;
let cacheTime = 0;
const CACHE_TTL = 60 * 1000;

async function getTools(env, origin) {
  const now = Date.now();
  if (cachedTools && now - cacheTime < CACHE_TTL) {
    return cachedTools;
  }
  const res = await env.ASSETS.fetch(new Request(`${origin}/tools.json`));
  if (!res.ok) throw new Error('Failed to load tools.json');
  cachedTools = await res.json();
  cacheTime = now;
  return cachedTools;
}

// 404 响应
async function render404(env, origin) {
  const nf = await env.ASSETS.fetch(new Request(`${origin}/404.html`));
  return new Response(await nf.text(), {
    status: 404,
    headers: { 'Content-Type': 'text/html; charset=utf-8' }
  });
}
