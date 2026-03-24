/* Meridian PWA — Service Worker */
var CACHE_VERSION = 'meridian-pwa-v1';
var SHELL_ASSETS = [
  '../pwa/styles.css',
  '../pwa/app.js',
  '../pwa/icon.svg',
];

self.addEventListener('install', function(event) {
  event.waitUntil(
    caches.open(CACHE_VERSION)
      .then(function(cache) { return cache.addAll(SHELL_ASSETS); })
      .then(function() { return self.skipWaiting(); })
  );
});

self.addEventListener('activate', function(event) {
  event.waitUntil(
    caches.keys().then(function(keys) {
      return Promise.all(
        keys.filter(function(k) { return k !== CACHE_VERSION; })
            .map(function(k) { return caches.delete(k); })
      );
    }).then(function() { return self.clients.claim(); })
  );
});

self.addEventListener('fetch', function(event) {
  var url = new URL(event.request.url);
  var path = url.pathname;

  /* Network-first for dynamic per-client data */
  if (path.endsWith('/config.json') ||
      path.endsWith('/sub.txt') ||
      path.indexOf('/stats/') !== -1) {
    event.respondWith(networkFirst(event.request));
    return;
  }

  /* Cache-first for shell assets and HTML */
  event.respondWith(cacheFirst(event.request));
});

function networkFirst(request) {
  return fetch(request).then(function(response) {
    if (response.ok) {
      var clone = response.clone();
      caches.open(CACHE_VERSION).then(function(cache) {
        cache.put(request, clone);
      });
    }
    return response;
  }).catch(function() {
    return caches.match(request);
  });
}

function cacheFirst(request) {
  return caches.match(request).then(function(cached) {
    if (cached) return cached;
    return fetch(request).then(function(response) {
      if (response.ok) {
        var clone = response.clone();
        caches.open(CACHE_VERSION).then(function(cache) {
          cache.put(request, clone);
        });
      }
      return response;
    }).catch(function() {
      return new Response('Offline', { status: 503, statusText: 'Service Unavailable' });
    });
  });
}
