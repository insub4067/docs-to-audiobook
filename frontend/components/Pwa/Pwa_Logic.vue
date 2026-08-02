<script lang="ts">
import type { PwaState } from "./Pwa_State.vue";
import { useAuthLogic } from "../../Auth/Auth_Logic.vue";
import { useToastLogic } from "../Toast/Toast_Logic.vue";
import { useToastState } from "../Toast/Toast_State.vue";

export interface PwaLogic {
    initialize(): void;
    onTouchStart(event: TouchEvent): void;
    onTouchMove(event: TouchEvent): void;
    onTouchEnd(): void;
    onTouchCancel(): void;
    dismissIosPrompt(): void;
}

const PULL_THRESHOLD = 64;
const PULL_MAX = 110;
const IOS_PROMPT_DISMISSED_KEY = "iosPwaPromptDismissed";

// static/js/pwa.js를 옮긴 것. 당겨서 새로고침, 배포 감지 후 자동 리로드,
// 서비스워커 버전 표시, iOS 홈 화면 추가 안내를 담당한다.
export function usePwaLogic(state: PwaState): PwaLogic {
    const authLogic = useAuthLogic();
    const { showToast } = useToastLogic(useToastState());

    let pullStartY = 0;
    let pullActive = false;
    let cachedBuildId: string | null = null;
    let lastVersionCheckTime = 0;

    function pullBlocked(): boolean {
        return state.isRefreshing.value
            || !!document.querySelector(".reader-overlay.show, .generation-modal.show, .action-sheet-backdrop.show");
    }

    function setPull(distance: number, progress: number): void {
        document.documentElement.classList.add("pull-active");
        document.documentElement.style.setProperty("--pull-y", `${distance}px`);
        state.pullOpacity.value = Math.min(progress * 1.4, 1);
        state.pullProgress.value = progress;
    }

    function resetPull(animated: boolean): void {
        state.isPullSettling.value = animated;
        document.documentElement.classList.toggle("pull-settling", animated);
        state.pullDistance.value = 0;
        document.documentElement.style.setProperty("--pull-y", "0px");
        state.pullOpacity.value = 0;

        const cleanup = () => {
            if (pullActive || state.isRefreshing.value) return;
            document.documentElement.classList.remove("pull-active", "pull-settling");
            document.documentElement.style.removeProperty("--pull-y");
            state.isPullSettling.value = false;
        };
        if (animated) setTimeout(cleanup, 400);
        else cleanup();
    }

    async function runRefresh(): Promise<void> {
        state.isRefreshing.value = true;
        state.isPullSettling.value = true;
        document.documentElement.classList.add("pull-active", "pull-settling");
        document.documentElement.style.setProperty("--pull-y", `${PULL_THRESHOLD}px`);
        state.pullOpacity.value = 1;

        const startedAt = Date.now();
        try {
            const syncFn = (window as any).__syncAudiobooksToCloud;
            if (authLogic.isLoggedIn() && typeof syncFn === "function") await syncFn();
            const renderFn = (window as any).__renderLibrary;
            if (typeof renderFn === "function") await renderFn();
        } catch (error) {
            console.error("새로고침 실패:", error);
        }
        const elapsed = Date.now() - startedAt;
        if (elapsed < 600) await new Promise((resolve) => setTimeout(resolve, 600 - elapsed));

        state.isRefreshing.value = false;
        resetPull(true);
    }

    function onTouchStart(event: TouchEvent): void {
        if (pullBlocked() || window.scrollY > 0 || event.touches.length !== 1) return;
        pullStartY = event.touches[0].clientY;
        pullActive = true;
        state.isPullSettling.value = false;
    }

    function onTouchMove(event: TouchEvent): void {
        if (!pullActive) return;
        const dy = event.touches[0].clientY - pullStartY;
        if (dy <= 0 || window.scrollY > 0) {
            pullActive = false;
            resetPull(true);
            return;
        }
        state.pullDistance.value = Math.min(dy * 0.5, PULL_MAX);
        setPull(state.pullDistance.value, Math.min(state.pullDistance.value / PULL_THRESHOLD, 1));
        if (event.cancelable) event.preventDefault();
    }

    function onTouchEnd(): void {
        if (!pullActive) return;
        pullActive = false;
        if (state.pullDistance.value >= PULL_THRESHOLD) runRefresh();
        else resetPull(true);
    }

    function onTouchCancel(): void {
        if (!pullActive) return;
        pullActive = false;
        resetPull(true);
    }

    async function fetchBuildId(): Promise<string | null> {
        try {
            const res = await fetch("/api/version", { cache: "no-store" });
            if (!res.ok) return null;
            const data = await res.json();
            return data.build_id || null;
        } catch {
            return null;
        }
    }

    async function checkAndReloadIfUpdated(): Promise<void> {
        if (!cachedBuildId) {
            cachedBuildId = await fetchBuildId();
            return;
        }
        const latestId = await fetchBuildId();
        if (latestId && latestId !== cachedBuildId) {
            showToast("리소스 업데이트 중", "info");
            setTimeout(() => {
                if ("serviceWorker" in navigator && navigator.serviceWorker.controller) {
                    caches.keys().then((keys) => {
                        Promise.all(keys.map((k) => caches.delete(k))).then(() => window.location.reload());
                    });
                } else {
                    window.location.reload();
                }
            }, 3000);
        }
    }

    function initIosPrompt(): void {
        const isIos = /iPad|iPhone|iPod/.test(navigator.userAgent) && !(window as any).MSStream;
        const isSafari = isIos && /WebKit/.test(navigator.userAgent) && !/CriOS/.test(navigator.userAgent) && !/FxiOS/.test(navigator.userAgent);
        const isStandalone = (window.navigator as any).standalone === true || window.matchMedia("(display-mode: standalone)").matches;
        const lastDismissed = localStorage.getItem(IOS_PROMPT_DISMISSED_KEY);
        const isDismissedRecently = !!lastDismissed && (Date.now() - parseInt(lastDismissed, 10)) < (7 * 24 * 60 * 60 * 1000);

        if (isSafari && !isStandalone && !isDismissedRecently) {
            setTimeout(() => { state.isIosPromptVisible.value = true; }, 1500);
        }
    }

    function dismissIosPrompt(): void {
        state.isIosPromptVisible.value = false;
        localStorage.setItem(IOS_PROMPT_DISMISSED_KEY, Date.now().toString());
    }

    function initialize(): void {
        fetchBuildId().then((id) => { cachedBuildId = id; });

        document.addEventListener("visibilitychange", () => {
            if (document.visibilityState !== "visible") return;
            checkAndReloadIfUpdated();
            (window as any).__checkPendingBackgroundJobs?.();
        });

        const appMain = document.querySelector(".app-main");
        appMain?.addEventListener("scroll", () => {
            const now = Date.now();
            if (now - lastVersionCheckTime > 30000) {
                lastVersionCheckTime = now;
                checkAndReloadIfUpdated();
            }
        }, { passive: true });

        fetch("/sw.js", { cache: "no-store" })
            .then((res) => res.text())
            .then((text) => {
                const match = text.match(/CACHE_NAME\s*=\s*["']([^"']+)["']/);
                if (match?.[1]) state.versionLabel.value = `v ${match[1]}`;
            })
            .catch((error) => console.error("Failed to fetch sw version:", error));

        initIosPrompt();
    }

    return { initialize, onTouchStart, onTouchMove, onTouchEnd, onTouchCancel, dismissIosPrompt };
}

export default {};
</script>
