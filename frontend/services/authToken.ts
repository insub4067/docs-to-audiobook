// 인증 토큰이 어디에 저장되고 어떤 헤더가 되는지를 아는 유일한 곳.
//
// 사용자 앱은 Auth_Logic.authHeaders()로 이미 한 곳에 모여 있었지만, 관리자
// SPA는 Auth_Logic을 쓰지 않아(사용자 앱의 로그인 흐름 전체를 끌고 온다)
// `Bearer ${localStorage.getItem("authToken")}`을 여덟 번 반복하고 있었다.
// 두 앱이 같은 지식을 공유하되 서로를 import하지 않도록 여기로 뺀다.

const AUTH_TOKEN_KEY = "authToken";

export function readAuthToken(): string | null {
    return localStorage.getItem(AUTH_TOKEN_KEY);
}

export function writeAuthToken(token: string): void {
    localStorage.setItem(AUTH_TOKEN_KEY, token);
}

export function clearAuthToken(): void {
    localStorage.removeItem(AUTH_TOKEN_KEY);
}

/** 다른 탭의 로그인/로그아웃을 감지하는 storage 이벤트가 이 키인지. */
export function isAuthTokenKey(key: string | null): boolean {
    return key === AUTH_TOKEN_KEY;
}

/** 토큰이 없으면 빈 객체 — 호출부가 스프레드로 그대로 붙일 수 있게 한다. */
export function authHeaders(): Record<string, string> {
    const token = readAuthToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
}
