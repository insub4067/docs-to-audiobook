import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

import AdminView from "../Admin/Admin_View.vue";
import type { LibraryJob } from "../Admin/Admin_State.vue";

const METRICS_RESPONSE = { weekly_active_users: 0 };

function jsonResponse(body: unknown) {
    return { ok: true, status: 200, json: async () => body };
}

let fetchMock: ReturnType<typeof vi.fn>;

/** 관리자 화면을 띄우고 등록 작업 목록만 원하는 값으로 채운다. */
async function mountAdminWithJobs(jobs: Partial<LibraryJob>[]) {
    fetchMock.mockImplementation(async (url: string) => {
        const path = String(url);
        if (path.startsWith("/api/admin/library/jobs")) return jsonResponse({ jobs });
        if (path.startsWith("/api/admin/library")) return jsonResponse({ items: [] });
        return jsonResponse(METRICS_RESPONSE);
    });

    const wrapper = mount(AdminView, { attachTo: document.body });
    // onMounted의 fetch 세 건이 끝나고 다시 렌더될 때까지 기다린다.
    await new Promise((resolve) => setTimeout(resolve, 0));
    await wrapper.vm.$nextTick();
    return wrapper;
}

beforeEach(() => {
    setActivePinia(createPinia());
    localStorage.clear();
    localStorage.setItem("authToken", "admin-token");
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
    vi.unstubAllGlobals();
});

// 예전에는 등록이 실패해도 audiobooks 행이 생기지 않아 서버 로그 말고는
// 아무 흔적이 없었다. 관리자 화면에서 무엇이 왜 실패했는지 보이고,
// 원문으로 다시 시도할 수 있어야 한다.
describe("관리자 등록 작업 목록", () => {
    it("실패한 작업의 사유와 다시 시도 버튼을 보여준다", async () => {
        const wrapper = await mountAdminWithJobs([
            { id: "job-1", title: "법구경", status: "error", error: "TimeoutError: TTS 요청 시간 초과", progress: null },
        ]);

        const text = wrapper.text();
        expect(text).toContain("법구경");
        expect(text).toContain("TTS 요청 시간 초과");
        expect(wrapper.findAll(".library-job-btn").map((btn) => btn.text())).toEqual(["다시 시도", "삭제"]);
    });

    it("진행 중인 작업은 진행률을 보여주고 재시도 버튼은 없다", async () => {
        const wrapper = await mountAdminWithJobs([
            { id: "job-1", title: "도덕경", status: "processing", error: null, progress: 43 },
        ]);

        expect(wrapper.text()).toContain("음성 생성 중 · 43%");
        expect(wrapper.findAll(".library-job-btn")).toHaveLength(0);
    });

    it("진행률을 아직 모르면 퍼센트 없이 상태만 보여준다", async () => {
        // 서버가 재시작되면 메모리에 있던 진행률이 사라진다. 그때 0%로
        // 보여주면 작업이 멈춘 것처럼 오해하게 된다.
        const wrapper = await mountAdminWithJobs([
            { id: "job-1", title: "도덕경", status: "processing", error: null, progress: null },
        ]);

        expect(wrapper.text()).toContain("음성 생성 중");
        expect(wrapper.text()).not.toContain("%");
    });

    it("다시 시도를 누르면 해당 작업의 retry를 호출한다", async () => {
        const wrapper = await mountAdminWithJobs([
            { id: "job-1", title: "법구경", status: "error", error: "실패", progress: null },
        ]);

        await wrapper.findAll(".library-job-btn")[0].trigger("click");

        const retryCall = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/jobs/job-1/retry"));
        expect(retryCall).toBeTruthy();
        expect((retryCall![1] as RequestInit).method).toBe("POST");
    });

    it("작업이 없으면 비어 있다고 알린다", async () => {
        const wrapper = await mountAdminWithJobs([]);

        expect(wrapper.text()).toContain("진행 중이거나 실패한 등록 작업이 없습니다.");
    });
});
