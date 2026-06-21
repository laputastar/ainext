// Serve detail.html for all /tools/* URLs, preserving browser URL
export async function onRequest(context) {
  const url = new URL(context.request.url);
  if (url.pathname === '/tools.json') return context.next();
  
  // Use ASSETS binding to fetch static detail.html
  const res = await context.env.ASSETS.fetch(
    new URL('/detail.html', url.origin),
    context.request
  );
  return res;
}
