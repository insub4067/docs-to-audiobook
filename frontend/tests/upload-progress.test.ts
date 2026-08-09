import { mount } from "@vue/test-utils";
import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";

import { postFormWithProgress } from "../services/uploadProgress";
import UploadBlockingOverlayView from "../components/Upload/UploadBlockingOverlay_View.vue";
import { useGenerationState } from "../Generation/Generation_State.vue";
import type { GenerationLogic } from "../Generation/Generation_Logic.vue";

// 큰 PDF를 올릴 때 "오래 걸리는데 진행 중인지 모르겠다"는 신고에서 나왔다.
// fetch는 업로드 진행률을 주지 않아 화면이 멈춘 것처럼 보였다.

/** XHR을 흉내낸다. 실제 네트워크 없이 진행 이벤트를 직접 쏜다. */
class FakeXhr {
    static last: FakeXhr | null = null;
    upload = { onprogress: null as ((e: object) => void) | null, onload: null as (() => void) | null };
    onload: (() => void) | null = null;
    onerror: (() => void) | null = null;
    ontimeout: (() => void) | null = null;
    status = 200;
    responseText = "{}";
    headers: Record<string, string> = {};
    aborted = false;
    sent: unknown = null;

    constructor() { FakeXhr.last = this; }
    open() {}
    setRequestHeader(name: string, value: string) { this.headers[name] = value; }
    send(body: unknown) { this.sent = body; }
    abort() { this.aborted = true; }

    /** 서버가 바이트를 받는 중 */
    emitProgress(loaded: number, total: number) {
        this.upload.onprogress?.({ lengthComputable: true, loaded, total });
    }
    /** 본문을 다 보낸 시점 */
    finishSending() { this.upload.onload?.(); }
    respond(status: number, body: unknown) {
        this.status = status;
        this.responseText = JSON.stringify(body);
        this.onload?.();
    }
}

beforeEach(() => {
    vi.stubGlobal("XMLHttpRequest", FakeXhr);
});

afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
});

describe("업로드 진행률 전송", () => {
    it("보낸 바이트만큼 퍼센트를 알린다", async () => {
        const seen: (number | null)[] = [];
        const promise = postFormWithProgress("/api/upload", new FormData(), {}, new AbortController().signal, (p) => seen.push(p));

        FakeXhr.last!.emitProgress(25, 100);
        FakeXhr.last!.emitProgress(80, 100);
        FakeXhr.last!.respond(200, { ok: true });
        await promise;

        expect(seen.slice(0, 2)).toEqual([25, 80]);
    });

    it("⚠️ 다 보내고 나면 null을 알려 진행률이 없는 구간임을 표시한다", async () => {
        // 서버가 텍스트를 뽑는 구간은 진행률을 알 수 없다. 여기서 100%로
        // 두면 막대가 꽉 찬 채 한참 멈춰 있어 "끝났는데 왜 안 넘어가지"가 된다.
        const seen: (number | null)[] = [];
        const promise = postFormWithProgress("/api/upload", new FormData(), {}, new AbortController().signal, (p) => seen.push(p));

        FakeXhr.last!.emitProgress(100, 100);
        FakeXhr.last!.finishSending();
        FakeXhr.last!.respond(200, { ok: true });
        await promise;

        expect(seen[seen.length - 1]).toBeNull();
    });

    it("총 크기를 모르면 퍼센트를 지어내지 않는다", async () => {
        const seen: (number | null)[] = [];
        const promise = postFormWithProgress("/api/upload", new FormData(), {}, new AbortController().signal, (p) => seen.push(p));

        FakeXhr.last!.upload.onprogress?.({ lengthComputable: false, loaded: 50, total: 0 });
        FakeXhr.last!.respond(200, {});
        await promise;

        expect(seen).toEqual([]);
    });

    it("서버 오류의 detail을 그대로 던진다", async () => {
        const promise = postFormWithProgress("/api/upload", new FormData(), {}, new AbortController().signal, () => {});
        FakeXhr.last!.respond(413, { detail: "문서가 너무 깁니다." });

        await expect(promise).rejects.toThrow("문서가 너무 깁니다.");
    });

    it("취소하면 요청을 끊고 AbortError로 거절한다", async () => {
        // 호출부의 cancelUpload와 isAbortError를 그대로 쓰려면 이름이 맞아야 한다.
        const controller = new AbortController();
        const promise = postFormWithProgress("/api/upload", new FormData(), {}, controller.signal, () => {});

        controller.abort();

        await expect(promise).rejects.toMatchObject({ name: "AbortError" });
        expect(FakeXhr.last!.aborted).toBe(true);
    });

    it("이미 취소된 상태면 요청을 보내지도 않는다", async () => {
        const controller = new AbortController();
        controller.abort();
        const before = FakeXhr.last;

        await expect(
            postFormWithProgress("/api/upload", new FormData(), {}, controller.signal, () => {}),
        ).rejects.toMatchObject({ name: "AbortError" });

        expect(FakeXhr.last).toBe(before);
    });

    it("헤더를 그대로 싣는다", async () => {
        const promise = postFormWithProgress("/api/scan-pdf", new FormData(), { "X-Scan-Id": "abc" }, new AbortController().signal, () => {});
        FakeXhr.last!.respond(200, {});
        await promise;

        expect(FakeXhr.last!.headers["X-Scan-Id"]).toBe("abc");
        // ⚠️ Content-Type은 넣으면 안 된다 — multipart 경계를 브라우저가 정한다.
        expect(FakeXhr.last!.headers["Content-Type"]).toBeUndefined();
    });
});

describe("업로드 대기 화면", () => {
    function setup() {
        const state = useGenerationState();
        state.isDropzoneLoading.value = true;
        const wrapper = mount(UploadBlockingOverlayView, {
            props: { state, logic: {} as GenerationLogic },
        });
        return { state, wrapper };
    }

    it("전송 중에는 실측 막대를 보여준다", async () => {
        const { state, wrapper } = setup();
        state.uploadPercent.value = 42;
        await wrapper.vm.$nextTick();

        expect(wrapper.find(".upload-progress-fill").attributes("style")).toContain("42%");
        expect(wrapper.text()).toContain("42%");
        wrapper.unmount();
    });

    it("고성능 PDF는 몇 쪽까지 왔는지 보여준다", async () => {
        const { state, wrapper } = setup();
        state.uploadPercent.value = null;
        state.scanPageProgress.value = { done: 12, total: 30 };
        await wrapper.vm.$nextTick();

        expect(wrapper.text()).toContain("12/30쪽");
        expect(wrapper.find(".upload-progress-fill").attributes("style")).toContain("40%");
        wrapper.unmount();
    });

    it("⚠️ 진행률을 모르는 구간에는 막대를 그리지 않는다", async () => {
        // 여기에 막대를 채우면 90%에서 멈춰 있는 흔한 거짓말이 된다.
        const { state, wrapper } = setup();
        state.uploadPercent.value = null;
        state.scanPageProgress.value = null;
        await wrapper.vm.$nextTick();

        expect(wrapper.find(".upload-progress-track").exists()).toBe(false);
        wrapper.unmount();
    });

    it("진행률이 없으면 경과 시간으로 살아있음을 보여준다", async () => {
        vi.useFakeTimers();
        const state = useGenerationState();
        const wrapper = mount(UploadBlockingOverlayView, {
            props: { state, logic: {} as GenerationLogic },
        });
        state.isDropzoneLoading.value = true;
        await wrapper.vm.$nextTick();

        await vi.advanceTimersByTimeAsync(3000);

        expect(wrapper.text()).toContain("3초째");
        wrapper.unmount();
        vi.useRealTimers();
    });
});
