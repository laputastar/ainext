// Serve detail.html for /tools/* URLs, preserving browser URL
export async function onRequestGet(context) {
  const url = new URL(context.request.url);
  if (url.pathname.startsWith('/tools.json')) {
    return context.next();
  }
  return context.env.ASSETS.fetch(new URL('/detail.html', context.request.url));
}
