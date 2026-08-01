const PENDING_BACKGROUND_JOBS_KEY = "textAudio_pendingBackgroundJobs";
const PUSH_SUBSCRIPTION_OWNER_KEY = "textAudio_pushSubscriptionOwner";
const BACKGROUND_JOB_CLAIM_MS = 5 * 60 * 1000;
const PUSH_UNSUBSCRIBE_TIMEOUT_MS = 2500;
const backgroundNotificationTabId = typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`;
let backgroundJobCheckInterval = null;
let checkingBackgroundJobs = false;
let backgroundNotificationMessageListenerAdded = false;
let pushNotificationContext = null;

function pendingBackgroundJobNamespace(userId = getCurrentAuthenticatedUserId()) {
    if (!userId) return null;
    return `${PENDING_BACKGROUND_JOBS_KEY}:${encodeURIComponent(userId)}:`;
}

function pendingBackgroundJobKey(userId, jobId) {
    return `${pendingBackgroundJobNamespace(userId)}job:${encodeURIComponent(jobId)}`;
}

function pendingBackgroundJobClaimKey(userId, jobId) {
    return `${pendingBackgroundJobNamespace(userId)}claim:${encodeURIComponent(jobId)}`;
}

function readPendingBackgroundJobs(userId = getCurrentAuthenticatedUserId()) {
    const namespace = pendingBackgroundJobNamespace(userId);
    if (!namespace) return [];
    const jobPrefix = `${namespace}job:`;
    const pending = [];
    for (let index = 0; index < localStorage.length; index++) {
        const key = localStorage.key(index);
        if (!key?.startsWith(jobPrefix) || localStorage.getItem(key) === null) continue;
        try {
            pending.push(decodeURIComponent(key.slice(jobPrefix.length)));
        } catch (error) {
            // 손상된 로컬 키는 상태 조회 대상에서 제외한다.
        }
    }
    return pending;
}

function readPendingBackgroundJobTitle(userId, jobId) {
    try {
        const value = JSON.parse(localStorage.getItem(pendingBackgroundJobKey(userId, jobId)) || "null");
        return typeof value?.title === "string" && value.title.trim() ? value.title : "오디오북";
    } catch (error) {
        return "오디오북";
    }
}

function rememberBackgroundJob(jobId, title = "오디오북") {
    const userId = getCurrentAuthenticatedUserId();
    if (!userId || typeof jobId !== "string" || !jobId) return;
    localStorage.setItem(pendingBackgroundJobKey(userId, jobId), JSON.stringify({ title }));
    updateBackgroundJobCheckInterval();
}

function forgetBackgroundJob(jobId, userId = getCurrentAuthenticatedUserId()) {
    if (!userId) return;
    localStorage.removeItem(pendingBackgroundJobKey(userId, jobId));
    updateBackgroundJobCheckInterval();
}

function updateBackgroundJobCheckInterval() {
    const hasPendingJobs = readPendingBackgroundJobs().length > 0;
    if (hasPendingJobs && !backgroundJobCheckInterval) {
        backgroundJobCheckInterval = setInterval(checkPendingBackgroundJobs, 30000);
    } else if (!hasPendingJobs && backgroundJobCheckInterval) {
        clearInterval(backgroundJobCheckInterval);
        backgroundJobCheckInterval = null;
    }
}

async function claimPendingBackgroundJob(userId, jobId) {
    const key = pendingBackgroundJobClaimKey(userId, jobId);
    const now = Date.now();
    try {
        const current = JSON.parse(localStorage.getItem(key) || "null");
        if (current?.expiresAt > now) return false;
        const claim = { owner: backgroundNotificationTabId, expiresAt: now + BACKGROUND_JOB_CLAIM_MS };
        localStorage.setItem(key, JSON.stringify(claim));
        await new Promise((resolve) => setTimeout(resolve, 50));
        return JSON.parse(localStorage.getItem(key) || "null")?.owner === backgroundNotificationTabId;
    } catch (error) {
        return false;
    }
}

function releasePendingBackgroundJobClaim(userId, jobId) {
    const key = pendingBackgroundJobClaimKey(userId, jobId);
    try {
        if (JSON.parse(localStorage.getItem(key) || "null")?.owner === backgroundNotificationTabId) {
            localStorage.removeItem(key);
        }
    } catch (error) {
        localStorage.removeItem(key);
    }
}

async function checkOnePendingBackgroundJob(userId, jobId, shouldClaim) {
    if (shouldClaim && !await claimPendingBackgroundJob(userId, jobId)) return;
    try {
        if (getCurrentAuthenticatedUserId() !== userId) return;
        const response = await fetch(`/api/background-jobs/${encodeURIComponent(jobId)}`, {
            headers: authHeaders(),
        });
        if (!response.ok || getCurrentAuthenticatedUserId() !== userId) return;
        const job = await response.json();
        if (job.status === "completed") {
            const syncAudiobooksToCloud = window.__syncAudiobooksToCloud;
            if (typeof syncAudiobooksToCloud !== "function") return;
            const syncResult = await syncAudiobooksToCloud({ silent: true });
            if (!syncResult?.ok || getCurrentAuthenticatedUserId() !== userId) return;
            forgetBackgroundJob(jobId, userId);
            window.__removeBackgroundJobLoading?.(jobId);
            showToast("오디오북 생성이 완료되었습니다.", "success");
        } else if (job.status === "error") {
            forgetBackgroundJob(jobId, userId);
            window.__removeBackgroundJobLoading?.(jobId);
            showToast(job.error || "오디오북 생성에 실패했습니다.", "error");
        }
    } catch (error) {
        console.warn("백그라운드 작업 상태 확인 실패");
    } finally {
        if (shouldClaim) releasePendingBackgroundJobClaim(userId, jobId);
    }
}

async function checkPendingBackgroundJobsForUser(userId, shouldClaim) {
    if (getCurrentAuthenticatedUserId() !== userId) return;
    for (const jobId of readPendingBackgroundJobs(userId)) {
        await checkOnePendingBackgroundJob(userId, jobId, shouldClaim);
    }
}

async function checkPendingBackgroundJobs() {
    const userId = getCurrentAuthenticatedUserId();
    if (!isLoggedIn() || !userId || checkingBackgroundJobs) return;
    checkingBackgroundJobs = true;
    try {
        if (navigator.locks?.request) {
            const lockName = `${PENDING_BACKGROUND_JOBS_KEY}:${encodeURIComponent(userId)}:check`;
            await navigator.locks.request(lockName, () => checkPendingBackgroundJobsForUser(userId, false));
        } else {
            await checkPendingBackgroundJobsForUser(userId, true);
        }
    } finally {
        checkingBackgroundJobs = false;
    }
}

function urlBase64ToUint8Array(value) {
    const padding = "=".repeat((4 - (value.length % 4)) % 4);
    const base64 = (value + padding).replace(/-/g, "+").replace(/_/g, "/");
    return Uint8Array.from(atob(base64), (character) => character.charCodeAt(0));
}

async function savePushSubscription(subscription) {
    const response = await fetch("/api/push/subscriptions", {
        method: "POST",
        headers: { ...authHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify(subscription.toJSON()),
    });
    if (!response.ok) throw new Error("구독 저장 실패");
}

async function deletePushSubscription(endpoint, signal) {
    const response = await fetch("/api/push/subscriptions", {
        method: "DELETE",
        headers: { ...authHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ endpoint }),
        signal,
    });
    if (!response.ok) throw new Error("구독 삭제 실패");
}

function renderPushNotificationState(button, label, state) {
    button.dataset.state = state;
    button.disabled = state === "blocked";
    button.setAttribute("aria-pressed", String(state === "on"));
    label.textContent = state === "on"
        ? "완료 알림 켜짐"
        : state === "blocked" ? "알림 차단됨" : "완료 알림 꺼짐";
}

async function requestPushNotificationSubscription() {
    const context = pushNotificationContext;
    if (!context) return false;
    if (context.subscriptionIsRegistered) return true;
    if (Notification.permission === "denied") {
        renderPushNotificationState(context.button, context.label, "blocked");
        return false;
    }

    let createdSubscription = false;
    try {
        const permissionRequest = Notification.permission === "granted"
            ? Promise.resolve("granted")
            : Notification.requestPermission();
        const permission = await permissionRequest;
        if (permission !== "granted") {
            renderPushNotificationState(
                context.button,
                context.label,
                permission === "denied" ? "blocked" : "off",
            );
            showToast("완료 알림 권한이 허용되지 않았습니다.", "error");
            return false;
        }

        createdSubscription = !context.subscription;
        if (createdSubscription) {
            context.subscription = await context.registration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: urlBase64ToUint8Array(context.config.public_key),
            });
        }
        await savePushSubscription(context.subscription);
        context.subscriptionIsRegistered = true;
        localStorage.setItem(PUSH_SUBSCRIPTION_OWNER_KEY, getCurrentAuthenticatedUserId());
        renderPushNotificationState(context.button, context.label, "on");
        showToast("완료 알림 켜짐", "success");
        return true;
    } catch (error) {
        if (createdSubscription && context.subscription) {
            await Promise.allSettled([context.subscription.unsubscribe()]);
            context.subscription = null;
        }
        context.subscriptionIsRegistered = false;
        renderPushNotificationState(
            context.button,
            context.label,
            Notification.permission === "denied" ? "blocked" : "off",
        );
        console.warn("푸시 알림 설정 실패");
        showToast("완료 알림 설정에 실패했습니다.", "error");
        return false;
    }
}

async function initializeBackgroundNotifications() {
    pushNotificationContext = null;
    window.__requestPushNotificationSubscription = requestPushNotificationSubscription;
    window.__checkPendingBackgroundJobs = checkPendingBackgroundJobs;
    window.__refreshBackgroundNotificationNamespace = () => {
        updateBackgroundJobCheckInterval();
        checkPendingBackgroundJobs();
    };
    const userId = getCurrentAuthenticatedUserId();
    for (const jobId of readPendingBackgroundJobs(userId)) {
        window.__showBackgroundJobLoading?.(jobId, readPendingBackgroundJobTitle(userId, jobId));
    }
    checkPendingBackgroundJobs();
    updateBackgroundJobCheckInterval();

    if ("serviceWorker" in navigator && !backgroundNotificationMessageListenerAdded) {
        navigator.serviceWorker.addEventListener("message", (event) => {
            if (event.data?.type === "check_pending_background_jobs") {
                window.__checkPendingBackgroundJobs?.();
            }
        });
        backgroundNotificationMessageListenerAdded = true;
    }

    const button = document.getElementById("pushNotificationBtn");
    const label = document.getElementById("pushNotificationLabel");
    if (
        !isLoggedIn()
        || !getCurrentAuthenticatedUserId()
        || !button
        || !label
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
            const userId = getCurrentAuthenticatedUserId();
            if (localStorage.getItem(PUSH_SUBSCRIPTION_OWNER_KEY) === userId) {
                subscriptionIsRegistered = true;
            } else {
                try {
                    await savePushSubscription(subscription);
                    localStorage.setItem(PUSH_SUBSCRIPTION_OWNER_KEY, userId);
                    subscriptionIsRegistered = true;
                } catch (error) {
                    console.warn("기존 푸시 알림 구독 연결 실패");
                }
            }
        }
        pushNotificationContext = {
            button,
            label,
            config,
            registration,
            subscription,
            subscriptionIsRegistered,
        };
        button.hidden = false;
        renderPushNotificationState(
            button,
            label,
            Notification.permission === "denied"
                ? "blocked"
                : subscriptionIsRegistered ? "on" : "off",
        );

        button.addEventListener("click", async () => {
            if (button.dataset.state === "blocked" || button.dataset.busy === "true") return;
            button.dataset.busy = "true";
            button.disabled = true;
            try {
                const context = pushNotificationContext;
                if (context?.subscription && button.dataset.state === "on") {
                    const { timedOut, result } = await runBoundedPushUnsubscribe(
                        (signal) => performSubscriptionUnsubscribe(context.subscription, signal),
                    );
                    if (timedOut || (!result.serverDisabled && !result.browserDisabled)) {
                        if (timedOut) localStorage.removeItem(PUSH_SUBSCRIPTION_OWNER_KEY);
                        context.subscription = await registration.pushManager.getSubscription();
                        if (context.subscription) {
                            renderPushNotificationState(button, label, "on");
                            throw new Error("구독 해제 실패");
                        }
                    }
                    context.subscription = null;
                    context.subscriptionIsRegistered = false;
                    localStorage.removeItem(PUSH_SUBSCRIPTION_OWNER_KEY);
                    renderPushNotificationState(button, label, "off");
                    showToast("완료 알림 꺼짐", "success");
                    return;
                }
                await requestPushNotificationSubscription();
            } catch (error) {
                console.warn("푸시 알림 설정 실패");
                showToast("완료 알림 설정에 실패했습니다.", "error");
            } finally {
                delete button.dataset.busy;
                if (button.dataset.state !== "blocked") button.disabled = false;
            }
        });
    } catch (error) {
        console.warn("푸시 알림 설정을 불러오지 못했습니다.");
    }
}

async function performSubscriptionUnsubscribe(subscription, signal) {
    const [browserResult, serverResult] = await Promise.allSettled([
        subscription.unsubscribe(),
        deletePushSubscription(subscription.endpoint, signal),
    ]);
    return {
        browserDisabled: browserResult.status === "fulfilled" && browserResult.value !== false,
        serverDisabled: serverResult.status === "fulfilled",
    };
}

async function performPushUnsubscribe(signal) {
    const registration = await navigator.serviceWorker.getRegistration();
    if (!registration) return;
    const subscription = await registration.pushManager.getSubscription();
    if (!subscription) return;
    const result = await performSubscriptionUnsubscribe(subscription, signal);
    if (result.browserDisabled || result.serverDisabled) {
        localStorage.removeItem(PUSH_SUBSCRIPTION_OWNER_KEY);
    }
}

async function runBoundedPushUnsubscribe(operation) {
    const controller = new AbortController();
    let timeoutId;
    const timeout = new Promise((resolve) => {
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
        clearTimeout(timeoutId);
    }
}

async function unsubscribePushNotifications() {
    localStorage.removeItem(PUSH_SUBSCRIPTION_OWNER_KEY);
    if (!("serviceWorker" in navigator)) return;
    try {
        await runBoundedPushUnsubscribe(performPushUnsubscribe);
    } catch (error) {
        // 로그아웃은 구독 해제 실패와 관계없이 계속한다.
    }
}
