// Serve detail.html for valid /tools/* URLs, 404 for invalid ones
export async function onRequest(context) {
  const url = new URL(context.request.url);
  if (url.pathname === '/tools.json') return context.next();
  
  // Extract tool ID from URL
  const m = url.pathname.match(/\/(\d+)\.html$/);
  if (m) {
    // Check if tool exists
    try {
      const tRes = await fetch(new URL('/tools.json', url.origin));
      const tools = await tRes.json();
      if (tools.some(t => String(t.id) === m[1])) {
        const res = await fetch(new URL('/detail.html', url.origin));
        const html = await res.text();
        return new Response(html, {headers: {'Content-Type': 'text/html; charset=utf-8'}});
      }
    } catch(e) { /* fall through to 404 */ }
  }
  
  // Tool doesn't exist — return 404 page
  const nf = await fetch(new URL('/404.html', url.origin));
  const nfHtml = await nf.text();
  return new Response(nfHtml, {status: 404, headers: {'Content-Type': 'text/html; charset=utf-8'}});
}
