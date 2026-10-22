'use strict';
// Cache only the generic offline page. Financial data, app HTML, API responses,
// and mutations always go to the server; never queue or replay financial writes.
const offlineURL = new URL('offline.html', self.registration.scope).href;
const cachePrefix = 'firefly-sidecar-' + encodeURIComponent(self.registration.scope) + '-';
const cacheName = cachePrefix + 'offline-v1';
self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(cacheName);
    await cache.add(new Request(offlineURL, {cache: 'reload'}));
    await self.skipWaiting();
  })());
});
self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    for (const name of await caches.keys()) {
      if (name.startsWith(cachePrefix) && name !== cacheName) await caches.delete(name);
    }
    await self.clients.claim();
  })());
});
self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== 'GET' || request.mode !== 'navigate' ||
      url.origin !== self.location.origin || !url.href.startsWith(self.registration.scope) ||
      url.pathname.startsWith(new URL('api/', self.registration.scope).pathname)) return;
  event.respondWith(fetch(request).catch(async () => {
    const cache = await caches.open(cacheName);
    return (await cache.match(offlineURL)) || Response.error();
  }));
});
