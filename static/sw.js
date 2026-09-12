const CACHE = 'bingo-comunidade-pwa-v1';
const STATIC_ASSETS = [
  '/static/style.css',
  '/static/v114.css',
  '/static/favicon.png',
  '/static/favicon.ico',
  '/static/logo_sistema_bc.png',
  '/static/pwa.js',
  '/offline'
];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(STATIC_ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const req = event.request;
  const url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/api/') || url.pathname.endsWith('.pdf') || url.pathname.endsWith('/qr.png')) return;
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(caches.match(req).then(cached => cached || fetch(req).then(resp => {
      const copy = resp.clone();
      caches.open(CACHE).then(cache => cache.put(req, copy));
      return resp;
    })));
    return;
  }
  if (req.mode === 'navigate') {
    event.respondWith(fetch(req).catch(() => caches.match('/offline')));
  }
});
