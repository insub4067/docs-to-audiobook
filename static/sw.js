const CACHE_NAME = "2026.08.01.25";

const ASSETS_TO_CACHE = [
  "/",
  "/static/style.css",
  "/static/app.js",
  "/static/admin.css",
  "/static/admin.js",
  "/static/admin-metric.js",
  "/static/textaudio-icon.png",
  "https://unpkg.com/lucide@latest",
  "https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=Noto+Sans+KR:wght@300;400;500;700&family=Playfair+Display:ital,wght@0,400..900;1,400..900&family=Noto+Serif+KR:wght@300;400;500;700&display=swap"
];

// Install Event
self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log("Caching essential assets...");
      return cache.addAll(ASSETS_TO_CACHE);
    }).then(() => self.skipWaiting())
  );
});

// Activate Event
self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  if (e.request.method !== "GET") {
    return;
  }

  // ✅ blob: 요청은 Service Worker가 절대 건드리지 않는다.
  // iOS WebKit에서 blob: 요청까지 fetch 이벤트로 넘어오는데,
  // blob:은 네트워크 리소스가 아니라 fetch(e.request)로 재요청하면 무조건 실패한다.
  if (e.request.url.startsWith("blob:")) {
    return;
  }

  const url = new URL(e.request.url);
  if (url.pathname.startsWith("/api/")) {
    return;
  }

  e.respondWith(
    fetch(e.request)
      .then((networkResponse) => {
        if (networkResponse.status === 200 && e.request.url.startsWith(self.location.origin)) {
          const responseClone = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(e.request, responseClone);
          });
        }
        return networkResponse;
      })
      .catch(() => {
        return caches.match(e.request).then((cachedResponse) => {
          if (cachedResponse) {
            return cachedResponse;
          }
          if (e.request.mode === "navigate") {
            return caches.match("/");
          }
        });
      })
  );
});
