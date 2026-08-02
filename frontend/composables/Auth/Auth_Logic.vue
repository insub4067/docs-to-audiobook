<script lang="ts">
import { useAuthStore, type AuthUser } from "../../stores/auth";
import { getAllAudiobooksFromDB } from "../../services/indexedDb";

export interface FetchUserError extends Error {
    authFailed?: boolean;
}

export interface AuthLogic {
    isLoggedIn(): boolean;
    authHeaders(): Record<string, string>;
    anonymousSessionHeaders(): Record<string, string>;
    canStartAnonymousTrial(): Promise<boolean>;
    trackProductEvent(eventName: string): void;
    fetchCurrentUser(token: string): Promise<AuthUser>;
    initializeAuth(): Promise<void>;
    completeSocialLogin(provider: string, token: string): Promise<void>;
    logout(): Promise<void>;
}

// static/js/auth.js 그대로. localStorage 키("authToken" 등)는 이미 로그인된
// 사용자가 있어 바꾸면 전부 로그아웃되므로 동일하게 유지한다.
const AUTH_TOKEN_KEY = "authToken";

/** 이 기기에 저장된 오디오북을 지운다. 기본 제공(isDefault)만 남기고
 * 재생 위치도 초기화한다. 정리 트랜잭션 완료 후 바로 닫기 위해
 * services/indexedDb.ts의 공용 연결과 별도로 자체 연결을 연다. */
function clearDeviceAudiobooks(): Promise<number> {
    return new Promise((resolve, reject) => {
        const req = indexedDB.open("AudiobookMakerDB", 1);
        req.onerror = () => reject(req.error);
        req.onsuccess = () => {
            const database = req.result;
            if (!database.objectStoreNames.contains("audiobooks")) {
                database.close();
                resolve(0);
                return;
            }
            const tx = database.transaction(["audiobooks"], "readwrite");
            const store = tx.objectStore("audiobooks");
            let removed = 0;

            store.openCursor().onsuccess = (e) => {
                const cursor = (e.target as IDBRequest<IDBCursorWithValue | null>).result;
                if (!cursor) return;
                if (cursor.value.isDefault) {
                    if (cursor.value.lastPosition) {
                        cursor.update({ ...cursor.value, lastPosition: 0 });
                    }
                } else {
                    cursor.delete();
                    removed++;
                }
                cursor.continue();
            };

            tx.oncomplete = () => { database.close(); resolve(removed); };
            tx.onerror = () => { database.close(); reject(tx.error); };
        };
    });
}

export function useAuthLogic(): AuthLogic {
    const store = useAuthStore();

    function isLoggedIn(): boolean {
        return !!localStorage.getItem(AUTH_TOKEN_KEY);
    }

    // 변환 계열 요청에 붙일 인증 헤더. FormData 전송 시 Content-Type을
    // 직접 지정하면 boundary가 깨지므로 Authorization만 넣는다.
    function authHeaders(): Record<string, string> {
        const token = localStorage.getItem(AUTH_TOKEN_KEY);
        return token ? { Authorization: `Bearer ${token}` } : {};
    }

    function anonymousSessionHeaders(): Record<string, string> {
        let sessionId = localStorage.getItem("anonymousSessionId");
        if (!sessionId) {
            sessionId = crypto.randomUUID();
            localStorage.setItem("anonymousSessionId", sessionId);
        }
        return { "X-Anonymous-Session": sessionId };
    }

    async function canStartAnonymousTrial(): Promise<boolean> {
        if (isLoggedIn()) return true;
        if (sessionStorage.getItem("anonymousTrialInProgress") === "true") return false;
        if (localStorage.getItem("anonymousTrialUsed") === "true") return false;
        const audiobooks = await getAllAudiobooksFromDB();
        return !audiobooks.some((audiobook) => !audiobook.isDefault);
    }

    function trackProductEvent(eventName: string): void {
        if (!isLoggedIn()) return;
        fetch("/api/events", {
            method: "POST",
            headers: { ...authHeaders(), "Content-Type": "application/json" },
            body: JSON.stringify({ event_name: eventName }),
        }).catch((error) => console.warn("제품 이벤트 기록 실패:", error));
    }

    /** 토큰이 실제로 무효한지(401/403) 여부를 호출자가 구분할 수 있도록
     * authFailed 플래그를 실어 던진다. 네트워크 실패나 5xx까지 로그아웃으로
     * 취급하면 재배포 중이거나 전파가 끊긴 순간에 앱을 열었다는 이유만으로
     * 세션이 사라진다. */
    async function fetchCurrentUser(token: string): Promise<AuthUser> {
        const response = await fetch("/api/auth/me", {
            headers: { Authorization: `Bearer ${token}` },
        });

        if (!response.ok) {
            const err: FetchUserError = new Error(`Failed to fetch user (${response.status})`);
            err.authFailed = response.status === 401 || response.status === 403;
            throw err;
        }

        return await response.json();
    }

    async function initializeAuth(): Promise<void> {
        const token = localStorage.getItem(AUTH_TOKEN_KEY);
        if (!token) {
            store.clearSession();
            return;
        }

        try {
            const user = await fetchCurrentUser(token);
            store.setSession(user, token);
        } catch (error) {
            const err = error as FetchUserError;
            if (err.authFailed) {
                // 토큰이 실제로 무효하다. 이때만 지운다.
                localStorage.removeItem(AUTH_TOKEN_KEY);
                store.clearSession();
            } else {
                // 네트워크 실패나 서버 일시 오류다. 토큰은 멀쩡하므로 지우지
                // 않고 로그인 상태를 유지한다. 재배포 중이거나 오프라인에서
                // 앱을 열었다는 이유로 세션이 사라지면 안 된다.
                console.warn("인증 확인 실패(일시적일 수 있음), 세션 유지:", error);
                store.setSession({ id: "", email: "", is_admin: false }, token);
            }
        }
    }

    /** 제공자가 발급한 토큰을 서버에 넘겨 우리 세션을 만든다. 제공자 공통 경로. */
    async function completeSocialLogin(provider: string, token: string): Promise<void> {
        const res = await fetch(`/api/auth/social/${provider}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ token }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "로그인 실패");

        localStorage.setItem(AUTH_TOKEN_KEY, data.access_token);
        await initializeAuth();
    }

    async function logout(): Promise<void> {
        // 기기 데이터를 지우는 동작이라 반드시 확인을 받는다.
        const confirmed = window.confirm(
            "로그아웃하면 이 기기에 저장된 오디오북이 모두 삭제됩니다.\n" +
            "기본 제공 오디오북만 남습니다.\n\n" +
            "삭제 전에 클라우드로 백업하며, 다시 로그인하면 복원됩니다.\n\n" +
            "계속하시겠습니까?"
        );
        if (!confirmed) return;

        // 지우기 전에 아직 안 올라간 것을 먼저 올린다. 이 단계를 건너뛰면
        // 복구할 방법이 없다. Library 기능이 포팅되면 window.__syncAudiobooksToCloud를
        // 등록한다 — 아직은 없으면 건너뛴다(동기화할 로컬 데이터가 없는
        // 상태와 동일하게 취급).
        const syncToCloud = (window as any).__syncAudiobooksToCloud as
            (() => Promise<{ ok: boolean }>) | undefined;
        if (syncToCloud) {
            let result: { ok: boolean };
            try {
                result = await syncToCloud();
            } catch (error) {
                console.error("로그아웃 전 백업 실패:", error);
                result = { ok: false };
            }
            if (!result.ok) {
                const proceed = window.confirm(
                    "클라우드 백업에 실패했습니다.\n" +
                    "지금 로그아웃하면 백업되지 않은 오디오북은 복구할 수 없습니다.\n\n" +
                    "그래도 로그아웃할까요?\n" +
                    "(취소를 누르고 잠시 후 다시 시도하는 것을 권합니다)"
                );
                if (!proceed) return;
            }
        }

        try {
            await clearDeviceAudiobooks();
        } catch (error) {
            // 삭제에 실패했는데 로그아웃만 되면 데이터가 남은 채 방치된다.
            console.error("기기 데이터 삭제 실패:", error);
            window.alert("기기 데이터를 삭제하지 못했습니다. 로그아웃을 취소합니다.");
            return;
        }

        const unsubscribePush = (window as any).__unsubscribePushNotifications as
            (() => Promise<void>) | undefined;
        if (unsubscribePush) {
            try {
                await unsubscribePush();
            } catch (error) {
                console.warn("푸시 알림 구독 해제 실패");
            }
        }

        // 재생 설정 등 사용자 흔적도 함께 정리한다
        localStorage.removeItem(AUTH_TOKEN_KEY);
        localStorage.removeItem("textAudio_playbackSpeed");
        localStorage.removeItem("textAudio_repeatMode");
        store.clearSession();
        location.reload();
    }

    return {
        isLoggedIn,
        authHeaders,
        anonymousSessionHeaders,
        canStartAnonymousTrial,
        trackProductEvent,
        fetchCurrentUser,
        initializeAuth,
        completeSocialLogin,
        logout,
    };
}

export default {};
</script>
