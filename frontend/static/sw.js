const CACHE_NAME = "2026.08.03.19";

const ASSETS_TO_CACHE = [
  "/",
  "/static/style.css",
  "/static/js/toast.js",
  "/static/js/utils.js",
  "/static/js/db.js",
  "/static/js/auth.js",
  "/static/js/pwa.js",
  "/static/js/notifications.js",
  "/static/js/generation-status.js",
  "/static/js/generation.js",
  "/static/js/voices.js",
  "/static/js/web-speech.js",
  "/static/js/reader-controls.js",
  "/static/js/reader.js",
  "/static/js/library.js",
  "/static/app.js",
  "/static/admin.css",
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

self.addEventListener("push", (event) => {
  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch (_) {}
  if (payload.type !== "audiobook_ready") return;

  event.waitUntil(
    Promise.all([
      self.registration.showNotification("TextAudio", {
        body: "오디오북 생성이 완료되었습니다.",
        icon: "/static/textaudio-icon.png",
        badge: "/static/textaudio-icon.png",
        tag: `audiobook-ready-${payload.job_id || "job"}`,
        data: { job_id: payload.job_id || "" },
      }),
      // 알림을 탭하지 않아도(포그라운드에서 보고 있는 중이거나, 백그라운드
      // 탭으로 열려 있는 경우) 열려 있는 모든 탭에 바로 알려서 "생성 중..."
      // 로딩 표시가 최대 30초 폴링을 기다리지 않고 즉시 사라지게 한다.
      // 이전에는 이 메시지가 notificationclick(알림을 직접 탭했을 때)에서만
      // 나갔다.
      clients.matchAll({ type: "window", includeUncontrolled: true }).then((windowClients) => {
        windowClients.forEach((client) => {
          client.postMessage({ type: "check_pending_background_jobs", job_id: payload.job_id || "" });
        });
      }),
    ])
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((windowClients) => {
      const client = windowClients.find((windowClient) => {
        try {
          return new URL(windowClient.url).origin === self.location.origin;
        } catch (_) {
          return false;
        }
      });
      if (client) {
        return client.focus().then(() => {
          client.postMessage({ type: "check_pending_background_jobs" });
        });
      }
      return clients.openWindow("/");
    })
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
