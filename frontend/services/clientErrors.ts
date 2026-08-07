// 클라이언트가 삼킨 실패를 서버에 한 줄 보고한다.
//
// 이 앱은 실패해도 재생이 끊기지 않도록 대부분의 오류를 console에만 남기고
// 넘어간다. 그 판단 자체는 맞지만, 그래서 "재생 위치가 몇 주 동안 한 건도
// 저장되지 않았다"는 사실을 아무도 몰랐다. console은 사용자 기기에만 있고
// 개발자는 그 화면을 볼 수 없다.
//
// 그래서 console.error는 그대로 두고(디버깅에는 여전히 필요하다) 서버에도
// 같은 내용을 보낸다. 관리자 지표 화면의 "조용한 실패"에서 볼 수 있다.

/** 서버 CLIENT_ERROR_LABELS와 짝이 맞아야 한다. 없는 값은 400으로 거절된다. */
export type ClientErrorScope =
    | "playback_save"
    | "product_event"
    | "generation"
    | "cloud_sync"
    | "default_book";

/** 같은 실패가 매초 반복되는 경우(재생 중 위치 저장이 계속 실패하는 등)
 *  서버로 초당 수십 건이 나간다. 같은 범위는 이 간격 안에 한 번만 보낸다. */
const THROTTLE_MS = 60_000;
const lastSentAt = new Map<ClientErrorScope, number>();

function describe(error: unknown): string {
    if (error instanceof Error) return `${error.name}: ${error.message}`;
    if (typeof error === "string") return error;
    try {
        return JSON.stringify(error);
    } catch {
        return String(error);
    }
}

export function reportClientError(scope: ClientErrorScope, error: unknown): void {
    const now = Date.now();
    const previous = lastSentAt.get(scope);
    if (previous !== undefined && now - previous < THROTTLE_MS) return;
    lastSentAt.set(scope, now);

    const token = localStorage.getItem("authToken");
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) headers.Authorization = `Bearer ${token}`;

    // 보고가 실패해도 아무것도 하지 않는다. 여기서 또 무언가를 시도하면
    // 실패 보고가 실패해 다시 보고하는 고리가 생긴다.
    fetch("/api/client-errors", {
        method: "POST",
        headers,
        body: JSON.stringify({ scope, message: describe(error) }),
        keepalive: true,
    }).catch(() => {});
}

/** `.catch(swallowed("playback_save", "재생 상태 저장 실패:"))` 형태로 쓴다.
 *  console.error는 그대로 남긴다 — 개발 중에는 그게 제일 빠른 단서다. */
export function swallowed(scope: ClientErrorScope, message: string) {
    return (error: unknown): void => {
        console.error(message, error);
        reportClientError(scope, error);
    };
}
