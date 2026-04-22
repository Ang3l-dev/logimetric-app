/* ═══════════════════════════════════════════════════════════════════
   LogiMetric — Service Worker
   Gestisce caching e offline per PWA
   ═══════════════════════════════════════════════════════════════════ */

const CACHE_NAME   = 'logimetric-v1';
const STATIC_CACHE = 'logimetric-static-v1';

/* Asset statici da pre-cachare */
const STATIC_ASSETS = [
  '/static/css/app.css',
  '/static/css/mobile.css',
  '/static/js/app.js',
  '/static/assets/favicon.svg',
  '/static/assets/logo.svg',
];

/* ── Install ── */
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then(cache => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

/* ── Activate ── */
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(k => k !== CACHE_NAME && k !== STATIC_CACHE)
          .map(k => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

/* ── Fetch ── */
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  /* Ignora richieste non-GET e cross-origin */
  if (request.method !== 'GET' || url.origin !== self.location.origin) return;

  /* Asset statici → cache first */
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(request).then(cached => {
        if (cached) return cached;
        return fetch(request).then(response => {
          const clone = response.clone();
          caches.open(STATIC_CACHE).then(cache => cache.put(request, clone));
          return response;
        });
      })
    );
    return;
  }

  /* Pagine HTML → network first, fallback a cache */
  if (request.headers.get('accept')?.includes('text/html')) {
    event.respondWith(
      fetch(request)
        .then(response => {
          /* Non cachare risposte non-ok o redirect */
          if (!response.ok || response.redirected) return response;
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(request, clone));
          return response;
        })
        .catch(() => caches.match(request))
    );
    return;
  }
});
