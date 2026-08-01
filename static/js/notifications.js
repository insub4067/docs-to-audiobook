const PENDING_BACKGROUND_JOBS_KEY = "textAudio_pendingBackgroundJobs";
let backgroundJobCheckInterval = null;
let checkingBackgroundJobs = false;

function readPendingBackgroundJobs() {
    try {
        const pending = JSON.parse(localStorage.getItem(PENDING_BACKGROUND_JOBS_KEY) || "[]");
        return Array.isArray(pending) ? pending.filter((jobId) => typeof jobId === "string") : [];
    } catch (error) {
        return [];
    }
}

function writePendingBackgroundJobs(jobIds) {
    localStorage.setItem(PENDING_BACKGROUND_JOBS_KEY, JSON.stringify(jobIds));
    updateBackgroundJobCheckInterval();
}

function rememberBackgroundJob(jobId) {
    const pending = readPendingBackgroundJobs();
    if (!pending.includes(jobId)) writePendingBackgroundJobs([...pending, jobId]);
}

function forgetBackgroundJob(jobId) {
    writePendingBackgroundJobs(readPendingBackgroundJobs().filter((pendingJobId) => pendingJobId !== jobId));
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

async function checkPendingBackgroundJobs() {
    if (!isLoggedIn() || checkingBackgroundJobs) return;
    checkingBackgroundJobs = true;
    try {
        for (const jobId of readPendingBackgroundJobs()) {
            try {
                const response = await fetch(`/api/background-jobs/${encodeURIComponent(jobId)}`, {
                    headers: authHeaders(),
                });
                if (!response.ok) continue;
                const job = await response.json();
                if (job.status === "completed") {
                    await window.__syncAudiobooksToCloud?.({ silent: true });
                    forgetBackgroundJob(jobId);
                    showToast("오디오북 생성이 완료되었습니다.", "success");
                } else if (job.status === "error") {
                    forgetBackgroundJob(jobId);
                    showToast(job.error || "오디오북 생성에 실패했습니다.", "error");
                }
            } catch (error) {
                console.warn("백그라운드 작업 상태 확인 실패");
            }
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

async function initializeBackgroundNotifications() {
    window.__checkPendingBackgroundJobs = checkPendingBackgroundJobs;
    checkPendingBackgroundJobs();
    updateBackgroundJobCheckInterval();

    const button = document.getElementById("pushNotificationBtn");
    const label = document.getElementById("pushNotificationLabel");
    if (!button || !label || !("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) return;

    try {
        const response = await fetch("/api/push/config");
        if (!response.ok) return;
        const config = await response.json();
        if (!config.enabled || !config.public_key) return;

        button.hidden = false;
        button.addEventListener("click", async () => {
            try {
                const permission = await Notification.requestPermission();
                if (permission !== "granted") {
                    showToast("완료 알림 권한이 허용되지 않았습니다.", "error");
                    return;
                }

                const registration = await navigator.serviceWorker.ready;
                let subscription = await registration.pushManager.getSubscription();
                if (!subscription) {
                    subscription = await registration.pushManager.subscribe({
                        userVisibleOnly: true,
                        applicationServerKey: urlBase64ToUint8Array(config.public_key),
                    });
                }
                await savePushSubscription(subscription);
                label.textContent = "완료 알림 켜짐";
                showToast("완료 알림 켜짐", "success");
            } catch (error) {
                console.warn("푸시 알림 설정 실패");
                showToast("완료 알림 설정에 실패했습니다.", "error");
            }
        });
    } catch (error) {
        console.warn("푸시 알림 설정을 불러오지 못했습니다.");
    }
}

async function unsubscribePushNotifications() {
    if (!("serviceWorker" in navigator)) return;

    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();
    if (!subscription) return;

    const endpoint = subscription.endpoint;
    try {
        await subscription.unsubscribe();
    } catch (error) {
        // 서버 구독 삭제는 계속 시도한다.
    }

    try {
        await fetch("/api/push/subscriptions", {
            method: "DELETE",
            headers: { ...authHeaders(), "Content-Type": "application/json" },
            body: JSON.stringify({ endpoint }),
        });
    } catch (error) {
        // 로그아웃은 구독 해제 실패와 관계없이 계속한다.
    }
}
