const CACHE_NAME = "2026.08.19.1";

// Vue SPA(/)의 JS/CSS는 파일명에 빌드 해시가 붙어(app-<hash>.js) 여기에
// 고정 경로로 적을 수 없다 — fetch 핸들러가 런타임에 캐시한다. 이 목록은
// 해시가 붙지 않는 자산만 담는다.
// ⚠️ 필수 자원과 선택 자원을 나눈 이유:
//
// cache.addAll()은 하나라도 실패하면 **전부** 실패한다. 예전에는 unpkg와
// Google Fonts가 이 목록에 함께 있어서, 남의 CDN이 잠깐 흔들리면 서비스
// 워커 설치 자체가 무산됐다 — 그러면 오프라인 캐시도 웹 푸시도 활성화되지
// 않는다. 우리 서버는 멀쩡한데 외부 CDN 때문에 앱이 앱답지 않게 된다.
//
// 우리 출처의 자원만 설치 성공 조건으로 두고, 외부 자원은 되면 좋고 안 되면
// 마는 것으로 내린다(둘 다 실패해도 아이콘 폰트가 늦게 뜰 뿐 동작한다).
const REQUIRED_ASSETS = [
  "/",
  "/static/admin.css",
  "/static/admin-metric.js",
  "/static/textaudio-icon.png"
];

const OPTIONAL_ASSETS = [
  "https://unpkg.com/lucide@latest",
  "https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=Noto+Sans+KR:wght@300;400;500;700&family=Playfair+Display:ital,wght@0,400..900;1,400..900&family=Noto+Serif+KR:wght@300;400;500;700&display=swap"
];

// Install Event
self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE_NAME).then((cache) =>
      // 필수 자원은 addAll — 하나라도 실패하면 설치가 실패하는 게 맞다.
      cache.addAll(REQUIRED_ASSETS).then(() =>
        // 외부 자원은 개별로, 실패는 삼킨다. allSettled라 하나가 깨져도
        // 나머지가 캐시되고 설치는 계속된다.
        Promise.allSettled(OPTIONAL_ASSETS.map((url) => cache.add(url)))
      )
    ).then(() => self.skipWaiting())
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

  if (payload.type === "news_ready") {
    event.waitUntil(
      self.registration.showNotification("TextAudio", {
        body: "새로운 경제 뉴스가 도착했어요.",
        icon: "/static/textaudio-icon.png",
        badge: "/static/textaudio-icon.png",
        tag: "news-ready",
        data: { url: "/" },
      })
    );
    return;
  }

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

  // ✅ 다른 origin(Supabase Storage의 서명된 오디오/문장 URL 등)도 SW가
  // 건드리지 않는다. 서명 토큰이 매 요청마다 달라 캐시 적중이 애초에
  // 불가능해 캐싱 이득이 없고, SW를 거치는 fetch()는 순간적인 네트워크
  // 끊김에도 재시도 없이 바로 실패해(catch에서 캐시 미스면 그냥 끝)
  // "공유 오디오를 불러올 수 없습니다" 같은 오류로 이어졌다. 브라우저가
  // 직접 요청하게 두면 더 안정적이다.
  if (!e.request.url.startsWith(self.location.origin)) {
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
