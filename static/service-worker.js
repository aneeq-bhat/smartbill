/* SmartBill service worker.
   - Static files (CSS, JS, icons) are cached for fast loading.
   - Pages and data are NEVER cached, so invoices and stock are always live
     and private. When the network is down an offline message is shown. */
const CACHE_NAME = "smartbill-static-v1";
const PRECACHE = [
  "/static/css/style.css",
  "/static/js/app.js",
  "/static/images/icon-192.png",
  "/static/images/icon-512.png"
];

const OFFLINE_PAGE =
  '<!doctype html><html lang="en"><head><meta charset="utf-8">' +
  '<meta name="viewport" content="width=device-width, initial-scale=1">' +
  "<title>SmartBill - offline</title>" +
  "<style>body{font-family:system-ui,sans-serif;background:#f6f8fc;color:#0b2a5b;" +
  "display:flex;min-height:100vh;align-items:center;justify-content:center;text-align:center;padding:1rem}" +
  "button{background:#0b2a5b;color:#fff;border:0;border-radius:8px;padding:.7rem 1.2rem;font-size:1rem}</style>" +
  "</head><body><div><h1>You are offline</h1>" +
  "<p>SmartBill needs an internet connection to reach the database.</p>" +
  '<button onclick="location.reload()">Try again</button></div></body></html>';

self.addEventListener("install", function (event) {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(function (cache) { return cache.addAll(PRECACHE); })
      .then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches.keys().then(function (names) {
      return Promise.all(names.filter(function (n) { return n !== CACHE_NAME; })
                              .map(function (n) { return caches.delete(n); }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener("fetch", function (event) {
  const request = event.request;
  if (request.method !== "GET") { return; }
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) { return; }

  if (request.mode === "navigate") {            // pages: network only
    event.respondWith(
      fetch(request).catch(function () {
        return new Response(OFFLINE_PAGE, { headers: { "Content-Type": "text/html; charset=utf-8" } });
      })
    );
    return;
  }

  if (url.pathname.indexOf("/static/") === 0) { // static files: cache, refresh in background
    event.respondWith(
      caches.open(CACHE_NAME).then(function (cache) {
        return cache.match(request).then(function (cached) {
          const network = fetch(request).then(function (response) {
            if (response && response.ok) { cache.put(request, response.clone()); }
            return response;
          }).catch(function () { return cached; });
          return cached || network;
        });
      })
    );
  }
});
