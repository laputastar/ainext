// Serve detail.html for all /tools/* URLs, preserving browser URL  
export async function onRequestGet(context) {
  const { request } = context;
  const url = new URL(request.url);
  if (url.pathname === '/tools.json') return context.next();
  
  // Fetch detail.html from origin
  const detailUrl = new URL('/detail.html', 'https://www.ainext.com');
  const res = await fetch(detailUrl);
  const html = await res.text();
  return new Response(html, {
    headers: { 'Content-Type': 'text/html; charset=utf-8' }
  });
}
