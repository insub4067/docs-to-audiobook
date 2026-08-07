import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

import AdminView from "../Admin/Admin_View.vue";
import type { ContentJob } from "../Admin/Admin_State.vue";

const METRICS_RESPONSE = { weekly_active_users: 0 };

function jsonResponse(body: unknown) {
    return { ok: true, status: 200, json: async () => body };
}

let fetchMock: ReturnType<typeof vi.fn>;

/** 관리자 화면을 띄우고 등록 작업 목록만 원하는 값으로 채운다. */
async function mountAdminWithJobs(jobs: Partial<ContentJob>[]) {
    fetchMock.mockImplementation(async (url: string) => {
        const path = String(url);
        if (path.startsWith("/api/admin/content-jobs")) return jsonResponse({ jobs });
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
            { id: "job-1", kind: "library", title: "법구경", status: "error", error: "TimeoutError: TTS 요청 시간 초과", progress: null },
        ]);

        const text = wrapper.text();
        expect(text).toContain("법구경");
        expect(text).toContain("TTS 요청 시간 초과");
        expect(wrapper.findAll(".library-job-btn").map((btn) => btn.text())).toEqual(["다시 시도", "삭제"]);
    });

    it("진행 중인 작업은 진행률을 보여주고 재시도 버튼은 없다", async () => {
        const wrapper = await mountAdminWithJobs([
            { id: "job-1", kind: "library", title: "도덕경", status: "processing", error: null, progress: 43 },
        ]);

        expect(wrapper.text()).toContain("음성 생성 중 · 43%");
        expect(wrapper.findAll(".library-job-btn")).toHaveLength(0);
    });

    it("진행률을 아직 모르면 퍼센트 없이 상태만 보여준다", async () => {
        // 서버가 재시작되면 메모리에 있던 진행률이 사라진다. 그때 0%로
        // 보여주면 작업이 멈춘 것처럼 오해하게 된다.
        const wrapper = await mountAdminWithJobs([
            { id: "job-1", kind: "library", title: "도덕경", status: "processing", error: null, progress: null },
        ]);

        expect(wrapper.text()).toContain("음성 생성 중");
        expect(wrapper.text()).not.toContain("%");
    });

    it("다시 시도를 누르면 해당 작업의 retry를 호출한다", async () => {
        const wrapper = await mountAdminWithJobs([
            { id: "job-1", kind: "library", title: "법구경", status: "error", error: "실패", progress: null },
        ]);

        await wrapper.findAll(".library-job-btn")[0].trigger("click");

        const retryCall = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/content-jobs/job-1/retry"));
        expect(retryCall).toBeTruthy();
        expect((retryCall![1] as RequestInit).method).toBe("POST");
    });

    it("뉴스와 작품을 한 목록에서 종류를 구분해 보여준다", async () => {
        // 경제 뉴스도 라이브러리와 같은 등록 경로를 타므로 한 목록에 섞인다.
        // 제목만 보면 어느 쪽인지 알 수 없어 종류 배지가 필요하다.
        const wrapper = await mountAdminWithJobs([
            { id: "job-1", kind: "news", title: "환율 급등", status: "processing", error: null, progress: 20 },
            { id: "job-2", kind: "library", title: "도덕경", status: "queued", error: null, progress: null },
        ]);

        expect(wrapper.findAll(".content-job-kind").map((el) => el.text())).toEqual(["뉴스", "작품"]);
        expect(wrapper.text()).toContain("환율 급등");
        expect(wrapper.text()).toContain("도덕경");
    });

    it("작업이 없으면 비어 있다고 알린다", async () => {
        const wrapper = await mountAdminWithJobs([]);

        expect(wrapper.text()).toContain("진행 중이거나 실패한 등록 작업이 없습니다.");
    });
});

// 작품 정보 수정 — 제목 오타 하나로 지우고 재등록(수 분짜리 재합성)하게
// 두지 않으려고 넣었다. 본문/음성은 여기서 못 바꾼다.
describe("작품 정보 수정", () => {
    async function mountWithItem() {
        const item = {
            id: "book-1", title: "도덕경", library_status: "review",
            library_category: "철학·사상", library_edition: "왕필본",
            library_translator: "오강남", library_source: null,
            library_rights: null, library_description: "노자의 도와 덕",
            created_at: "2026-08-01",
        };
        fetchMock.mockImplementation(async (url: string) => {
            const path = String(url);
            if (path.startsWith("/api/admin/content-jobs")) return jsonResponse({ jobs: [] });
            if (path.startsWith("/api/admin/library")) return jsonResponse({ items: [item] });
            return jsonResponse({});
        });
        const wrapper = mount(AdminView, { attachTo: document.body });
        await new Promise((resolve) => setTimeout(resolve, 0));
        await wrapper.vm.$nextTick();
        return wrapper;
    }

    async function openEditor(wrapper: Awaited<ReturnType<typeof mountWithItem>>) {
        await wrapper.find(".row-more-btn").trigger("click");
        await wrapper.vm.$nextTick();
        const edit = wrapper.findAll(".action-sheet-btn").find((b) => b.text() === "작품 정보 수정")!;
        await edit.trigger("click");
        await wrapper.vm.$nextTick();
    }

    it("기존 값을 폼에 채운다", async () => {
        const wrapper = await mountWithItem();
        await openEditor(wrapper);

        const values = wrapper.findAll(".admin-input").map((el) => (el.element as HTMLInputElement).value);
        expect(values).toContain("도덕경");
        expect(values).toContain("왕필본");
        expect(values).toContain("오강남");
    });

    it("저장하면 PATCH로 보낸다", async () => {
        const wrapper = await mountWithItem();
        await openEditor(wrapper);

        const title = wrapper.findAll(".admin-input")[0];
        await title.setValue("도덕경(개정)");
        const save = wrapper.findAll(".action-sheet-btn").find((b) => b.text() === "저장")!;
        await save.trigger("click");
        await new Promise((resolve) => setTimeout(resolve, 0));

        const patch = fetchMock.mock.calls.find(([, init]) => (init as RequestInit)?.method === "PATCH");
        expect(patch).toBeTruthy();
        expect(JSON.parse((patch![1] as RequestInit).body as string).title).toBe("도덕경(개정)");
    });

    it("제목을 비우면 저장하지 않는다", async () => {
        const wrapper = await mountWithItem();
        await openEditor(wrapper);

        await wrapper.findAll(".admin-input")[0].setValue("   ");
        await wrapper.findAll(".action-sheet-btn").find((b) => b.text() === "저장")!.trigger("click");
        await new Promise((resolve) => setTimeout(resolve, 0));

        expect(fetchMock.mock.calls.find(([, init]) => (init as RequestInit)?.method === "PATCH")).toBeUndefined();
    });
});
