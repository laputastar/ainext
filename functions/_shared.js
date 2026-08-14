// _shared.js — SSR shared utilities (imported by tools/[slug].js and category/[slug].js)
// ⚠️ CF Pages Functions 只能 import functions/ 目录内的文件

let cachedTools = null;
let cacheTime = 0;
const CACHE_TTL = 5 * 60 * 1000; // 5 min

let cachedSlim = null;
let slimTime = 0;
const SLIM_TTL = 5 * 60 * 1000; // 5 min

// 通过 KV 按 ID 读取单个工具（主路径）
export async function getTool(env, toolId) {
  if (!env.TOOLS) return null;
  const raw = await env.TOOLS.get(`tool:${toolId}`, { type: 'text' });
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

// 读取 tools-slim.json（列表/related 用，字段轻量）
export async function getSlim(env, origin) {
  const now = Date.now();
  if (cachedSlim && now - slimTime < SLIM_TTL) return cachedSlim;
  const res = await env.ASSETS.fetch(new Request(`${origin}/tools-slim.json`));
  if (!res.ok) throw new Error('Failed to load tools-slim.json');
  cachedSlim = await res.json();
  slimTime = now;
  return cachedSlim;
}

// 全量读取（兜底路径：KV 不可用或迁移期）
export async function getTools(env, origin) {
  const now = Date.now();
  if (cachedTools && now - cacheTime < CACHE_TTL) return cachedTools;
  const res = await env.ASSETS.fetch(new Request(`${origin}/tools.json.gz`));
  if (!res.ok) {
    // 迁移期兜底：gz 未生成时读旧 tools.json
    const fallback = await env.ASSETS.fetch(new Request(`${origin}/tools.json`));
    if (!fallback.ok) throw new Error('Failed to load tools data');
    cachedTools = await fallback.json();
    cacheTime = now;
    return cachedTools;
  }
  // 解压 gzip（Workers 原生支持 DecompressionStream）
  const blob = await res.blob();
  const decompressed = await new Response(blob.stream().pipeThrough(new DecompressionStream('gzip'))).text();
  cachedTools = JSON.parse(decompressed);
  cacheTime = now;
  return cachedTools;
}

export async function getCategories(env, origin) {
  const res = await env.ASSETS.fetch(new Request(`${origin}/categories.json`));
  if (!res.ok) throw new Error('Failed to load categories.json');
  const data = await res.json();
  return data.categories || data;
}

export async function render404(env, origin) {
  const nf = await env.ASSETS.fetch(new Request(`${origin}/404.html`));
  return new Response(await nf.text(), {
    status: 404,
    headers: {
      'Content-Type': 'text/html; charset=utf-8',
      'X-Frame-Options': 'SAMEORIGIN',
      'X-Content-Type-Options': 'nosniff',
      'Referrer-Policy': 'strict-origin-when-cross-origin'
    }
  });
}
