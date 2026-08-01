// -------------------------------------------------------
// 당겨서 새로고침 (iOS 스타일)
//
// body가 스크롤 주체다. 목록의 스와이프 삭제는 가로 이동만 처리하므로
// (|deltaX| > |deltaY| 조건) 세로 당김과는 충돌하지 않는다.
// -------------------------------------------------------
const pullEl = document.getElementById("pullRefresh");
if (pullEl) {
    const PULL_THRESHOLD = 64;   // 이만큼 당기고 놓으면 새로고침
    const PULL_MAX = 110;        // 이 이상은 더 안 내려간다
    const SPOKES = 12;

    let pullStartY = 0;
    let pullDistance = 0;
    let pullActive = false;      // 당김 제스처 추적 중
    let refreshing = false;

    const spokes = [...pullEl.querySelectorAll(".pull-spinner i")];
    // 스피너와 콘텐츠가 같은 값을 읽어야 하므로 공통 조상에 둔다
    const root = document.documentElement;

    function setPull(distance, progress) {
        root.classList.add("pull-active");
        root.style.setProperty("--pull-y", `${distance}px`);
        pullEl.style.opacity = String(Math.min(progress * 1.4, 1));
        // 진행도만큼 스포크를 차례로 켠다
        const lit = Math.round(progress * SPOKES);
        spokes.forEach((s, i) => { s.style.opacity = i < lit ? "1" : "0.15"; });
    }

    function resetPull(animated) {
        const animate = animated !== false;
        pullEl.classList.toggle("settling", animate);
        root.classList.toggle("pull-settling", animate);
        pullEl.classList.remove("refreshing");
        pullDistance = 0;
        root.style.setProperty("--pull-y", "0px");
        pullEl.style.opacity = "0";
        spokes.forEach(s => { s.style.opacity = ""; });

        // 되돌아간 뒤에는 transform을 완전히 걷어낸다. 남겨두면 콘텐츠에
        // 스택 컨텍스트가 계속 붙어 있게 된다.
        const cleanup = () => {
            if (pullActive || refreshing) return;
            root.classList.remove("pull-active", "pull-settling");
            root.style.removeProperty("--pull-y");
            pullEl.classList.remove("settling");
        };
        if (animate) setTimeout(cleanup, 400);
        else cleanup();
    }

    // 다른 화면이 떠 있으면 당김을 잡지 않는다
    function pullBlocked() {
        return refreshing
            || document.getElementById("readerOverlay").classList.contains("show")
            || document.getElementById("generationModal").classList.contains("show")
            || document.getElementById("actionSheetBackdrop").classList.contains("show");
    }

    window.addEventListener("touchstart", (e) => {
        if (pullBlocked() || window.scrollY > 0 || e.touches.length !== 1) return;
        pullStartY = e.touches[0].clientY;
        pullActive = true;
        pullEl.classList.remove("settling");
    }, { passive: true });

    window.addEventListener("touchmove", (e) => {
        if (!pullActive) return;
        const dy = e.touches[0].clientY - pullStartY;

        // 위로 밀거나 스크롤이 시작되면 당김이 아니다
        if (dy <= 0 || window.scrollY > 0) {
            pullActive = false;
            resetPull(true);
            return;
        }

        // 고무줄 저항: 당길수록 덜 따라온다
        pullDistance = Math.min(dy * 0.5, PULL_MAX);
        setPull(pullDistance, Math.min(pullDistance / PULL_THRESHOLD, 1));

        // 네이티브 오버스크롤(고무줄)이 같이 일어나면 어색하므로 막는다
        if (e.cancelable) e.preventDefault();
    }, { passive: false });

    async function runRefresh() {
        refreshing = true;
        pullEl.classList.add("settling", "refreshing");
        root.classList.add("pull-active", "pull-settling");
        // 새로고침 중에는 콘텐츠가 임계 지점에 머물러 스피너 자리를 만든다
        root.style.setProperty("--pull-y", `${PULL_THRESHOLD}px`);
        pullEl.style.opacity = "1";
        spokes.forEach(s => { s.style.opacity = ""; });

        const startedAt = Date.now();
        try {
            if (isLoggedIn() && typeof window.__syncAudiobooksToCloud === "function") {
                await window.__syncAudiobooksToCloud();
            }
            if (typeof window.__renderLibrary === "function") {
                await window.__renderLibrary();
            }
        } catch (err) {
            console.error("새로고침 실패:", err);
        }
        // 너무 빨리 끝나면 깜빡이는 것처럼 보인다. 최소 표시 시간을 준다.
        const elapsed = Date.now() - startedAt;
        if (elapsed < 600) await new Promise(r => setTimeout(r, 600 - elapsed));

        refreshing = false;
        resetPull(true);
    }

    window.addEventListener("touchend", () => {
        if (!pullActive) return;
        pullActive = false;
        if (pullDistance >= PULL_THRESHOLD) {
            runRefresh();
        } else {
            resetPull(true);
        }
    }, { passive: true });

    // 시스템 제스처 등으로 강제 종료되면 원위치로 되돌린다
    window.addEventListener("touchcancel", () => {
        if (!pullActive) return;
        pullActive = false;
        resetPull(true);
    }, { passive: true });
}

// -------------------------------------------------------
// Background → Foreground 복귀 시 배포 업데이트 감지
// 서버가 재시작(재배포)되면 build_id가 바뀌어 자동 리로드
// -------------------------------------------------------
let cachedBuildId = null;

async function fetchBuildId() {
    try {
        const res = await fetch("/api/version", { cache: "no-store" });
        if (!res.ok) return null;
        const data = await res.json();
        return data.build_id || null;
    } catch (e) {
        return null; // 네트워크 오프라인이면 조용히 무시
    }
}

// 최초 로드 시 build_id 기억
fetchBuildId().then(id => { cachedBuildId = id; });

let lastVersionCheckTime = 0;

// 버전 확인 및 업데이트 로직 (공통)
async function checkAndReloadIfUpdated() {
    if (!cachedBuildId) {
        cachedBuildId = await fetchBuildId();
        return;
    }
    const latestId = await fetchBuildId();
    if (latestId && latestId !== cachedBuildId) {
        // 새 배포 감지 → 토스트 알림 후 3초 뒤 리로드
        showToast("리소스 업데이트 중", "info");
        setTimeout(() => {
            // Service Worker 캐시도 함께 비우고 리로드
            if ("serviceWorker" in navigator && navigator.serviceWorker.controller) {
                caches.keys().then(keys => {
                    Promise.all(keys.map(k => caches.delete(k))).then(() => {
                        window.location.reload();
                    });
                });
            } else {
                window.location.reload();
            }
        }, 3000);
    }
}

// 앱이 포그라운드로 돌아올 때마다 체크
document.addEventListener("visibilitychange", async () => {
    if (document.visibilityState !== "visible") return;
    checkAndReloadIfUpdated();
});

// 메인 화면에서 스크롤 다운할 때도 버전 확인 (30초마다 한 번)
const appMain = document.querySelector(".app-main");
if (appMain) {
    appMain.addEventListener("scroll", () => {
        const now = Date.now();
        if (now - lastVersionCheckTime > 30000) { // 30초 이상 지났으면 확인
            lastVersionCheckTime = now;
            checkAndReloadIfUpdated();
        }
    }, { passive: true });
}

const appVersionDisplay = document.getElementById("appVersionDisplay");

// ----------------------------------------------------
// Fetch and display Service Worker version
// Display app version from sw.js CACHE_NAME
if (appVersionDisplay) {
    fetch("/sw.js", { cache: "no-store" })
        .then(res => res.text())
        .then(text => {
            const match = text.match(/CACHE_NAME\s*=\s*["']([^"']+)["']/);
            if (match && match[1]) {
                appVersionDisplay.textContent = `v ${match[1]}`;
            } else {
                console.warn("Could not find CACHE_NAME in sw.js");
            }
        })
        .catch(err => console.error("Failed to fetch sw version:", err));
} else {
    console.warn("appVersionDisplay element not found");
}

// iOS PWA Install Prompt
function initIosPwaPrompt() {
    const promptEl = document.getElementById("iosPwaPrompt");
    const closeBtn = document.getElementById("pwaCloseBtn");
    if (!promptEl || !closeBtn) return;

    // iOS 기기 감지
    const isIos = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
    // Safari 브라우저 감지 (Chrome 등 기타 웹뷰 제외)
    const isSafari = isIos && /WebKit/.test(navigator.userAgent) && !/CriOS/.test(navigator.userAgent) && !/FxiOS/.test(navigator.userAgent);

    // PWA Standalone 모드 여부 감지
    const isStandalone = window.navigator.standalone === true || window.matchMedia('(display-mode: standalone)').matches;

    // 이전에 닫기를 누른 기록이 있는지 확인 (7일)
    const lastDismissed = localStorage.getItem("iosPwaPromptDismissed");
    const isDismissedRecently = lastDismissed && (Date.now() - parseInt(lastDismissed, 10)) < (7 * 24 * 60 * 60 * 1000);

    if (isSafari && !isStandalone && !isDismissedRecently) {
        setTimeout(() => {
            promptEl.classList.add("show");
        }, 1500);
    }

    closeBtn.addEventListener("click", () => {
        promptEl.classList.remove("show");
        localStorage.setItem("iosPwaPromptDismissed", Date.now().toString());
    });
}
