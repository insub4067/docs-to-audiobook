<script lang="ts">
import { useAuthStore } from "../stores/auth";
import { useAuthLogic } from "../Auth/Auth_Logic.vue";
import { useToastLogic } from "../components/Toast/Toast_Logic.vue";
import { useToastState } from "../components/Toast/Toast_State.vue";
import type { NotificationsState } from "./Notifications_State.vue";

export interface NotificationsLogic {
    initialize(): Promise<void>;
    togglePush(): Promise<void>;
    requestPushNotificationSubscription(): Promise<boolean>;
    unsubscribePushNotifications(): Promise<void>;
}

const PENDING_BACKGROUND_JOBS_KEY = "textAudio_pendingBackgroundJobs";
const PUSH_SUBSCRIPTION_OWNER_KEY = "textAudio_pushSubscriptionOwner";
const BACKGROUND_JOB_CLAIM_MS = 5 * 60 * 1000;
const PUSH_UNSUBSCRIBE_TIMEOUT_MS = 2500;
const backgroundNotificationTabId = crypto.randomUUID();

let backgroundJobCheckInterval: ReturnType<typeof setInterval> | null = null;
let checkingBackgroundJobs = false;
let backgroundNotificationMessageListenerAdded = false;

interface PushNotificationContext {
    config: { public_key: string };
    registration: ServiceWorkerRegistration;
    subscription: PushSubscription | null;
    subscriptionIsRegistered: boolean;
}
let pushNotificationContext: PushNotificationContext | null = null;

function urlBase64ToUint8Array(value: string): Uint8Array {
    const padding = "=".repeat((4 - (value.length % 4)) % 4);
    const base64 = (value + padding).replace(/-/g, "+").replace(/_/g, "/");
    return Uint8Array.from(atob(base64), (character) => character.charCodeAt(0));
}

// static/js/notifications.js를 옮긴 것. 백그라운드(대용량) 작업 완료를
// 여러 탭에 걸쳐 폴링/중복방지(claim)하는 부분과 웹 푸시 구독 관리를
// 담당한다. 사용자 식별은 이제 Pinia authStore에서 가져온다(원본의
// getCurrentAuthenticatedUserId 대응).
export function useNotificationsLogic(state: NotificationsState): NotificationsLogic {
    const authStore = useAuthStore();
    const authLogic = useAuthLogic();
    const { showToast } = useToastLogic(useToastState());

    function currentUserId(): string | null {
        return authStore.isLoggedIn && authStore.user?.id ? authStore.user.id : null;
    }

    function pendingBackgroundJobNamespace(userId: string | null = currentUserId()): string | null {
        if (!userId) return null;
        return `${PENDING_BACKGROUND_JOBS_KEY}:${encodeURIComponent(userId)}:`;
    }

    function pendingBackgroundJobKey(userId: string | null, jobId: string): string {
        return `${pendingBackgroundJobNamespace(userId)}job:${encodeURIComponent(jobId)}`;
    }

    function pendingBackgroundJobClaimKey(userId: string | null, jobId: string): string {
        return `${pendingBackgroundJobNamespace(userId)}claim:${encodeURIComponent(jobId)}`;
    }

    function readPendingBackgroundJobs(userId: string | null = currentUserId()): string[] {
        const namespace = pendingBackgroundJobNamespace(userId);
        if (!namespace) return [];
        const jobPrefix = `${namespace}job:`;
        const pending: string[] = [];
        for (let index = 0; index < localStorage.length; index++) {
            const key = localStorage.key(index);
            if (!key?.startsWith(jobPrefix) || localStorage.getItem(key) === null) continue;
            try {
                pending.push(decodeURIComponent(key.slice(jobPrefix.length)));
            } catch {
                // 손상된 로컬 키는 상태 조회 대상에서 제외한다.
            }
        }
        return pending;
    }

    function readPendingBackgroundJobTitle(userId: string | null, jobId: string): string {
        try {
            const value = JSON.parse(localStorage.getItem(pendingBackgroundJobKey(userId, jobId)) || "null");
            return typeof value?.title === "string" && value.title.trim() ? value.title : "오디오북";
        } catch {
            return "오디오북";
        }
    }

    function readPendingBackgroundJobFolderId(userId: string | null, jobId: string): string | null {
        try {
            const value = JSON.parse(localStorage.getItem(pendingBackgroundJobKey(userId, jobId)) || "null");
            return typeof value?.folderId === "string" ? value.folderId : null;
        } catch {
            return null;
        }
    }

    function updateBackgroundJobCheckInterval(): void {
        const hasPendingJobs = readPendingBackgroundJobs().length > 0;
        if (hasPendingJobs && !backgroundJobCheckInterval) {
            backgroundJobCheckInterval = setInterval(checkPendingBackgroundJobs, 30000);
        } else if (!hasPendingJobs && backgroundJobCheckInterval) {
            clearInterval(backgroundJobCheckInterval);
            backgroundJobCheckInterval = null;
        }
    }

    function rememberBackgroundJob(jobId: string, title = "오디오북", folderId: string | null = null): void {
        const userId = currentUserId();
        if (!userId || typeof jobId !== "string" || !jobId) return;
        localStorage.setItem(pendingBackgroundJobKey(userId, jobId), JSON.stringify({ title, folderId }));
        updateBackgroundJobCheckInterval();
    }

    function forgetBackgroundJob(jobId: string, userId: string | null = currentUserId()): void {
        if (!userId) return;
        localStorage.removeItem(pendingBackgroundJobKey(userId, jobId));
        updateBackgroundJobCheckInterval();
    }

    async function claimPendingBackgroundJob(userId: string, jobId: string): Promise<boolean> {
        const key = pendingBackgroundJobClaimKey(userId, jobId);
        const now = Date.now();
        try {
            const current = JSON.parse(localStorage.getItem(key) || "null");
            if (current?.expiresAt > now) return false;
            const claim = { owner: backgroundNotificationTabId, expiresAt: now + BACKGROUND_JOB_CLAIM_MS };
            localStorage.setItem(key, JSON.stringify(claim));
            await new Promise((resolve) => setTimeout(resolve, 50));
            return JSON.parse(localStorage.getItem(key) || "null")?.owner === backgroundNotificationTabId;
        } catch {
            return false;
        }
    }

    function releasePendingBackgroundJobClaim(userId: string, jobId: string): void {
        const key = pendingBackgroundJobClaimKey(userId, jobId);
        try {
            if (JSON.parse(localStorage.getItem(key) || "null")?.owner === backgroundNotificationTabId) {
                localStorage.removeItem(key);
            }
        } catch {
            localStorage.removeItem(key);
        }
    }

    async function checkOnePendingBackgroundJob(userId: string, jobId: string, shouldClaim: boolean): Promise<void> {
        if (shouldClaim && !(await claimPendingBackgroundJob(userId, jobId))) return;
        try {
            if (currentUserId() !== userId) return;
            const response = await fetch(`/api/background-jobs/${encodeURIComponent(jobId)}`, {
                headers: authLogic.authHeaders(),
            });
            if (!response.ok || currentUserId() !== userId) return;
            const job = await response.json();
            if (job.status === "completed") {
                const syncFn = (window as any).__syncAudiobooksToCloud;
                if (typeof syncFn !== "function") return;
                const syncResult = await syncFn({ silent: true });
                if (!syncResult?.ok || currentUserId() !== userId) return;
                forgetBackgroundJob(jobId, userId);
                (window as any).__removeBackgroundJobLoading?.(jobId);
                // 백그라운드 생성은 즉시 응답 후 종료되므로 Generation_Logic의
                // generation_completed를 타지 않는다. 여기서 찍지 않으면
                // generation_started만 쌓여 생성 성공률이 실제보다 낮게 보인다.
                authLogic.trackProductEvent("generation_completed");
                showToast("오디오북 생성이 완료되었습니다.", "success");
            } else if (job.status === "error") {
                forgetBackgroundJob(jobId, userId);
                (window as any).__removeBackgroundJobLoading?.(jobId);
                authLogic.trackProductEvent("generation_failed");
                showToast(job.error || "오디오북 생성에 실패했습니다.", "error");
            }
        } catch {
            console.warn("백그라운드 작업 상태 확인 실패");
        } finally {
            if (shouldClaim) releasePendingBackgroundJobClaim(userId, jobId);
        }
    }

    async function checkPendingBackgroundJobsForUser(userId: string, shouldClaim: boolean): Promise<void> {
        if (currentUserId() !== userId) return;
        for (const jobId of readPendingBackgroundJobs(userId)) {
            await checkOnePendingBackgroundJob(userId, jobId, shouldClaim);
        }
    }

    async function checkPendingBackgroundJobs(): Promise<void> {
        const userId = currentUserId();
        if (!authLogic.isLoggedIn() || !userId || checkingBackgroundJobs) return;
        checkingBackgroundJobs = true;
        try {
            if ((navigator as any).locks?.request) {
                const lockName = `${PENDING_BACKGROUND_JOBS_KEY}:${encodeURIComponent(userId)}:check`;
                await (navigator as any).locks.request(lockName, () => checkPendingBackgroundJobsForUser(userId, false));
            } else {
                await checkPendingBackgroundJobsForUser(userId, true);
            }
        } finally {
            checkingBackgroundJobs = false;
        }
    }

    async function savePushSubscription(subscription: PushSubscription): Promise<void> {
        const response = await fetch("/api/push/subscriptions", {
            method: "POST",
            headers: { ...authLogic.authHeaders(), "Content-Type": "application/json" },
            body: JSON.stringify(subscription.toJSON()),
        });
        if (!response.ok) throw new Error("구독 저장 실패");
    }

    async function deletePushSubscription(endpoint: string, signal?: AbortSignal): Promise<void> {
        const response = await fetch("/api/push/subscriptions", {
            method: "DELETE",
            headers: { ...authLogic.authHeaders(), "Content-Type": "application/json" },
            body: JSON.stringify({ endpoint }),
            signal,
        });
        if (!response.ok) throw new Error("구독 삭제 실패");
    }

    async function requestPushNotificationSubscription(): Promise<boolean> {
        const context = pushNotificationContext;
        if (!context) return false;
        if (context.subscriptionIsRegistered) return true;
        if (Notification.permission === "denied") {
            state.pushState.value = "blocked";
            return false;
        }

        let createdSubscription = false;
        try {
            const permission = Notification.permission === "granted" ? "granted" : await Notification.requestPermission();
            if (permission !== "granted") {
                state.pushState.value = permission === "denied" ? "blocked" : "off";
                showToast("완료 알림 권한이 허용되지 않았습니다.", "error");
                return false;
            }

            createdSubscription = !context.subscription;
            if (createdSubscription) {
                context.subscription = await context.registration.pushManager.subscribe({
                    userVisibleOnly: true,
                    applicationServerKey: urlBase64ToUint8Array(context.config.public_key) as unknown as BufferSource,
                });
            }
            await savePushSubscription(context.subscription!);
            context.subscriptionIsRegistered = true;
            localStorage.setItem(PUSH_SUBSCRIPTION_OWNER_KEY, currentUserId() || "");
            state.pushState.value = "on";
            showToast("완료 알림 켜짐", "success");
            return true;
        } catch (error) {
            if (createdSubscription && context.subscription) {
                await Promise.allSettled([context.subscription.unsubscribe()]);
                context.subscription = null;
            }
            context.subscriptionIsRegistered = false;
            state.pushState.value = (Notification.permission as NotificationPermission) === "denied" ? "blocked" : "off";
            console.warn("푸시 알림 설정 실패");
            showToast("완료 알림 설정에 실패했습니다.", "error");
            return false;
        }
    }

    async function performSubscriptionUnsubscribe(subscription: PushSubscription, signal?: AbortSignal): Promise<{ browserDisabled: boolean; serverDisabled: boolean }> {
        const [browserResult, serverResult] = await Promise.allSettled([
            subscription.unsubscribe(),
            deletePushSubscription(subscription.endpoint, signal),
        ]);
        return {
            browserDisabled: browserResult.status === "fulfilled" && browserResult.value !== false,
            serverDisabled: serverResult.status === "fulfilled",
        };
    }

    async function runBoundedPushUnsubscribe<T>(operation: (signal: AbortSignal) => Promise<T>): Promise<{ timedOut: boolean; result: T | null }> {
        const controller = new AbortController();
        let timeoutId: ReturnType<typeof setTimeout>;
        const timeout = new Promise<{ timedOut: boolean; result: null }>((resolve) => {
            timeoutId = setTimeout(() => {
                controller.abort();
                resolve({ timedOut: true, result: null });
            }, PUSH_UNSUBSCRIBE_TIMEOUT_MS);
        });
        try {
            return await Promise.race([
                operation(controller.signal).then((result) => ({ timedOut: false, result })),
                timeout,
            ]);
        } finally {
            clearTimeout(timeoutId!);
        }
    }

    async function togglePush(): Promise<void> {
        if (state.pushState.value === "blocked" || state.isPushBusy.value) return;
        state.isPushBusy.value = true;
        try {
            const context = pushNotificationContext;
            if (context?.subscription && state.pushState.value === "on") {
                const { timedOut, result } = await runBoundedPushUnsubscribe((signal) => performSubscriptionUnsubscribe(context.subscription!, signal));
                if (timedOut || (!result?.serverDisabled && !result?.browserDisabled)) {
                    if (timedOut) localStorage.removeItem(PUSH_SUBSCRIPTION_OWNER_KEY);
                    context.subscription = await context.registration.pushManager.getSubscription();
                    if (context.subscription) {
                        state.pushState.value = "on";
                        throw new Error("구독 해제 실패");
                    }
                }
                context.subscription = null;
                context.subscriptionIsRegistered = false;
                localStorage.removeItem(PUSH_SUBSCRIPTION_OWNER_KEY);
                state.pushState.value = "off";
                showToast("완료 알림 꺼짐", "success");
                return;
            }
            await requestPushNotificationSubscription();
        } catch (error) {
            console.warn("푸시 알림 설정 실패");
            showToast("완료 알림 설정에 실패했습니다.", "error");
        } finally {
            state.isPushBusy.value = false;
        }
    }

    async function performPushUnsubscribe(signal?: AbortSignal): Promise<void> {
        const registration = await navigator.serviceWorker.getRegistration();
        if (!registration) return;
        const subscription = await registration.pushManager.getSubscription();
        if (!subscription) return;
        const result = await performSubscriptionUnsubscribe(subscription, signal);
        if (result.browserDisabled || result.serverDisabled) localStorage.removeItem(PUSH_SUBSCRIPTION_OWNER_KEY);
    }

    async function unsubscribePushNotifications(): Promise<void> {
        localStorage.removeItem(PUSH_SUBSCRIPTION_OWNER_KEY);
        if (!("serviceWorker" in navigator)) return;
        try {
            await runBoundedPushUnsubscribe(performPushUnsubscribe);
        } catch {
            // 로그아웃은 구독 해제 실패와 관계없이 계속한다.
        }
    }

    async function initialize(): Promise<void> {
        pushNotificationContext = null;
        (window as any).__requestPushNotificationSubscription = requestPushNotificationSubscription;
        (window as any).__checkPendingBackgroundJobs = checkPendingBackgroundJobs;
        (window as any).__rememberBackgroundJob = rememberBackgroundJob;
        (window as any).__unsubscribePushNotifications = unsubscribePushNotifications;
        (window as any).__refreshBackgroundNotificationNamespace = () => {
            updateBackgroundJobCheckInterval();
            checkPendingBackgroundJobs();
        };

        const userId = currentUserId();
        for (const jobId of readPendingBackgroundJobs(userId)) {
            (window as any).__showBackgroundJobLoading?.(
                jobId, readPendingBackgroundJobTitle(userId, jobId), readPendingBackgroundJobFolderId(userId, jobId),
            );
        }
        checkPendingBackgroundJobs();
        updateBackgroundJobCheckInterval();

        if ("serviceWorker" in navigator && !backgroundNotificationMessageListenerAdded) {
            navigator.serviceWorker.addEventListener("message", (event) => {
                if (event.data?.type === "check_pending_background_jobs") {
                    (window as any).__checkPendingBackgroundJobs?.();
                }
            });
            backgroundNotificationMessageListenerAdded = true;
        }

        if (
            !authLogic.isLoggedIn()
            || !currentUserId()
            || !("serviceWorker" in navigator)
            || !("PushManager" in window)
            || !("Notification" in window)
        ) return;

        try {
            const response = await fetch("/api/push/config");
            if (!response.ok) return;
            const config = await response.json();
            if (!config.enabled || !config.public_key) return;

            const registration = await navigator.serviceWorker.ready;
            const subscription = await registration.pushManager.getSubscription();
            let subscriptionIsRegistered = false;
            if (!subscription) {
                localStorage.removeItem(PUSH_SUBSCRIPTION_OWNER_KEY);
            } else if (Notification.permission !== "denied") {
                const uid = currentUserId();
                if (localStorage.getItem(PUSH_SUBSCRIPTION_OWNER_KEY) === uid) {
                    subscriptionIsRegistered = true;
                } else {
                    try {
                        await savePushSubscription(subscription);
                        localStorage.setItem(PUSH_SUBSCRIPTION_OWNER_KEY, uid || "");
                        subscriptionIsRegistered = true;
                    } catch {
                        console.warn("기존 푸시 알림 구독 연결 실패");
                    }
                }
            }
            pushNotificationContext = { config, registration, subscription, subscriptionIsRegistered };
            state.isPushVisible.value = true;
            state.pushState.value = Notification.permission === "denied" ? "blocked" : (subscriptionIsRegistered ? "on" : "off");
        } catch {
            console.warn("푸시 알림 설정을 불러오지 못했습니다.");
        }
    }

    return { initialize, togglePush, requestPushNotificationSubscription, unsubscribePushNotifications };
}

export default {};
</script>
