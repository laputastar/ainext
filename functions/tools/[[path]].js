// Serve detail.html for all /tools/* URLs, preserving browser URL
export async function onRequest(context) {
  const url = new URL(context.request.url);
  if (url.pathname === '/tools.json') return context.next();
  const res = await fetch(new URL('/detail.html', url.origin));
  const html = await res.text();
  return new Response(html, {headers: {'Content-Type': 'text/html; charset=utf-8'}});
}
