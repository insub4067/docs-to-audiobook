import { createPinia, setActivePinia } from "pinia";
import { describe, it, expect, beforeEach, vi } from "vitest";

import { useGenerationState } from "../Generation/Generation_State.vue";
import { useGenerationLogic } from "../Generation/Generation_Logic.vue";
import { resetAppConfigCache } from "../services/appConfig";
import type { VoiceLogic } from "../Voices/Voice_Logic.vue";

// 파일을 골랐는데 아무 일도 일어나지 않던 문제.
//
// 호출부(Home_View.onFileInputChange)는 input.files를 그대로 넘긴 뒤 곧바로
// input.value = ""로 입력창을 비운다. files는 복사본이 아니라 살아있는
// FileList라 그 순간 함께 비워진다.
//
// handleBatchFileSelect가 동기적으로 읽던 시절에는 문제가 없었다. 업로드
// 상한을 서버에서 받아오도록 바꾸면서 함수 첫 줄에 await가 생겼고, 거기서
// 양보한 사이에 목록이 비워져 재개 시점에는 처리할 파일이 하나도 남지
// 않았다 — 에러도 요청도 토스트도 없이 조용히 끝난다.
//
// 관측 대상은 "업로드가 시도됐는가"다. 업로드 성공 여부는 이 버그와 무관하고,
// 실패하면 상태가 되돌려져 화면 상태로는 구분할 수 없다.

const SERVER_LIMITS = {
    providers: {},
    google_client_id: "",
    google_api_key: "",
    upload_limit_bytes: 10 * 1024 * 1024,
    admin_upload_limit_bytes: 250 * 1024 * 1024,
};

/** 업로드는 XHR로 나간다. 보낸 URL만 기록하고 곧바로 성공 응답을 준다. */
class RecordingXhr {
    static urls: string[] = [];
    upload = { onprogress: null as ((e: object) => void) | null, onload: null as (() => void) | null };
    onload: (() => void) | null = null;
    onerror: (() => void) | null = null;
    ontimeout: (() => void) | null = null;
    status = 200;
    responseText = JSON.stringify({
        text_id: "t1", filename: "t.txt", char_count: 2,
        preview: "본문", text_access_token: "tok",
    });
    open(_method: string, url: string) { RecordingXhr.urls.push(url); }
    setRequestHeader() {}
    send() {
        this.upload.onload?.();
        this.onload?.();
    }
    abort() {}
}

function textFile(name = "t.txt"): File {
    return new File(["본문"], name, { type: "text/plain" });
}

function makeLogic() {
    const state = useGenerationState();
    const voiceLogic = { getSelectedVoice: () => "ko-KR-HyunsuNeural" } as unknown as VoiceLogic;
    return { state, logic: useGenerationLogic(state, voiceLogic) };
}

beforeEach(() => {
    setActivePinia(createPinia());
    resetAppConfigCache();
    RecordingXhr.urls = [];
    vi.stubGlobal("XMLHttpRequest", RecordingXhr);
    // /api/config가 한 틱 뒤에 응답해야 await가 실제로 양보한다 — 그래야
    // 경쟁 조건이 재현된다.
    vi.stubGlobal("fetch", vi.fn(() =>
        Promise.resolve({ ok: true, json: () => Promise.resolve(SERVER_LIMITS) })
    ));
});

describe("파일 선택 경쟁 조건", () => {
    it("넘긴 목록이 곧바로 비워져도 파일을 놓치지 않는다", async () => {
        const { logic } = makeLogic();

        // 살아있는 FileList를 흉내낸다. 호출부가 input.value = ""로 비우는 것과
        // 같은 일을, await가 양보한 직후에 일으킨다.
        const live: File[] = [textFile()];
        const pending = logic.handleBatchFileSelect(live);
        live.length = 0; // ← input.value = "" 가 하는 일

        await pending;

        expect(RecordingXhr.urls.some((u) => u.includes("/api/upload"))).toBe(true);
    });

    it("목록이 그대로 남아 있는 경우도 물론 동작한다", async () => {
        const { logic } = makeLogic();

        await logic.handleBatchFileSelect([textFile("keep.txt")]);

        expect(RecordingXhr.urls.some((u) => u.includes("/api/upload"))).toBe(true);
    });
});
