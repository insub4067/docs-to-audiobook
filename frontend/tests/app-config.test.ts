import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

import { loadAppConfig, resetAppConfigCache, uploadLimitBytes } from "../services/appConfig";

// 백엔드 state.py의 실제 값. 이 테스트가 검증하는 건 "프론트가 서버 값을
// 그대로 쓰는가"이지 숫자 자체가 아니라, 여기서만 리터럴로 쓴다.
const SERVER_LIMITS = {
    upload_limit_bytes: 10 * 1024 * 1024,
    admin_upload_limit_bytes: 250 * 1024 * 1024,
};

let fetchMock: ReturnType<typeof vi.fn>;

function configResponse(body: Record<string, unknown>) {
    return { ok: true, json: () => Promise.resolve(body) };
}

beforeEach(() => {
    resetAppConfigCache();
    fetchMock = vi.fn().mockResolvedValue(configResponse({ providers: {}, ...SERVER_LIMITS }));
    vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
    vi.restoreAllMocks();
});

describe("업로드 상한", () => {
    it("관리자에게 서버가 내려준 관리자 상한을 그대로 준다", async () => {
        // 프론트가 자체 상수(예전엔 50MB)를 들고 있으면 여기서 어긋난다.
        expect(await uploadLimitBytes(true)).toBe(SERVER_LIMITS.admin_upload_limit_bytes);
    });

    it("일반 사용자에게는 일반 상한을 준다", async () => {
        expect(await uploadLimitBytes(false)).toBe(SERVER_LIMITS.upload_limit_bytes);
    });

    it("설정을 못 받으면 null을 줘서 미리 거르지 않게 한다", async () => {
        // 임의의 기본값을 정해두면 그게 다시 두 번째 출처가 된다. 상한은
        // 서버가 업로드 스트림에서 강제하므로 여기선 통과시키는 게 맞다.
        fetchMock.mockRejectedValue(new Error("offline"));

        expect(await uploadLimitBytes(true)).toBeNull();
    });
});

describe("설정 캐시", () => {
    it("여러 번 불러도 한 번만 요청한다", async () => {
        await Promise.all([loadAppConfig(), loadAppConfig()]);
        await loadAppConfig();

        expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    it("실패는 캐시하지 않아 다음 호출이 다시 시도한다", async () => {
        fetchMock.mockRejectedValueOnce(new Error("offline"));
        await expect(loadAppConfig()).rejects.toThrow("offline");

        await expect(loadAppConfig()).resolves.toMatchObject(SERVER_LIMITS);
        expect(fetchMock).toHaveBeenCalledTimes(2);
    });
});
