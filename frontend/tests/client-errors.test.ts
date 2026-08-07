import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";

import { reportClientError, swallowed } from "../services/clientErrors";

function bodyOf(call: unknown[]): Record<string, unknown> {
    return JSON.parse((call[1] as RequestInit).body as string);
}

function reports(fetchMock: ReturnType<typeof vi.fn>) {
    return fetchMock.mock.calls.filter(([url]) => String(url) === "/api/client-errors");
}

let fetchMock: ReturnType<typeof vi.fn>;

// 스로틀 기록은 모듈 전역이라 테스트 사이에 남는다. 가짜 시계를 켜면 매번
// 같은 시각에서 시작하므로, 앞 테스트가 남긴 기록이 다음 테스트의 첫 보고를
// 막아 버린다. 테스트마다 시계를 스로틀 창 밖으로 밀어 격리한다.
let clock = Date.now();

beforeEach(() => {
    vi.useFakeTimers();
    clock += 10 * 60_000;
    vi.setSystemTime(clock);
    localStorage.clear();
    fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
});

describe("조용한 실패 보고", () => {
    it("Error를 이름과 메시지로 풀어서 보낸다", () => {
        reportClientError("generation", new TypeError("x is not a function"));

        expect(bodyOf(reports(fetchMock)[0])).toEqual({
            scope: "generation",
            message: "TypeError: x is not a function",
        });
    });

    it("로그인 상태면 토큰을 함께 보낸다", () => {
        localStorage.setItem("authToken", "토큰값");

        reportClientError("cloud_sync", new Error("실패"));

        const headers = (reports(fetchMock)[0][1] as RequestInit).headers as Record<string, string>;
        expect(headers.Authorization).toBe("Bearer 토큰값");
    });

    it("비로그인이어도 보고한다", () => {
        // 가입만 하고 이탈한 사용자가 무엇에 걸렸는지가 가장 알고 싶은 것이다.
        reportClientError("default_book", new Error("실패"));

        const headers = (reports(fetchMock)[0][1] as RequestInit).headers as Record<string, string>;
        expect(reports(fetchMock)).toHaveLength(1);
        expect(headers.Authorization).toBeUndefined();
    });

    it("같은 범위가 연달아 실패해도 1분에 한 번만 보낸다", () => {
        // 재생 중 위치 저장은 30초마다 시도한다. 스로틀이 없으면 한 번
        // 망가진 세션 하나가 서버로 수백 건을 쏟아붓는다.
        reportClientError("playback_save", new Error("1회"));
        reportClientError("playback_save", new Error("2회"));
        reportClientError("playback_save", new Error("3회"));

        expect(reports(fetchMock)).toHaveLength(1);
    });

    it("1분이 지나면 다시 보낸다", () => {
        reportClientError("playback_save", new Error("1회"));
        vi.advanceTimersByTime(60_001);
        reportClientError("playback_save", new Error("2회"));

        expect(reports(fetchMock)).toHaveLength(2);
    });

    it("범위가 다르면 서로 막지 않는다", () => {
        reportClientError("cloud_sync", new Error("동기화"));
        reportClientError("generation", new Error("생성"));

        expect(reports(fetchMock)).toHaveLength(2);
    });

    it("보고 자체가 실패해도 예외를 던지지 않는다", async () => {
        // 여기서 다시 무언가를 시도하면 실패 보고가 실패해 또 보고하는 고리가 생긴다.
        fetchMock.mockRejectedValue(new Error("네트워크 없음"));

        expect(() => reportClientError("generation", new Error("실패"))).not.toThrow();
        await vi.runAllTimersAsync();
    });

    it("swallowed는 console.error를 남기면서 보고까지 한다", () => {
        // console.error를 빼면 개발 중 디버깅이 어려워지고,
        // 보고를 빼면 원래 문제로 돌아간다. 둘 다여야 한다.
        swallowed("playback_save", "재생 상태 저장 실패:")(new Error("500"));

        expect(console.error).toHaveBeenCalledWith("재생 상태 저장 실패:", expect.any(Error));
        expect(reports(fetchMock)).toHaveLength(1);
    });
});
