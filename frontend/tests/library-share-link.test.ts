// 서점 작품 공유 링크(/?library=<id>).
//
// 공유 버튼이 만드는 주소를 받는 쪽이 없어서, 링크를 눌러도 홈에 그대로
// 머물렀다. 주소를 만드는 쪽과 읽는 쪽이 갈리면 이렇게 조용히 아무 일도
// 일어나지 않는다 — 여기서 둘이 맞물리는지 확인한다.
import { createPinia, setActivePinia } from "pinia";
import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";

import { useLibraryState, type LibraryItem } from "../Library/Library_State.vue";
import { useLibraryLogic } from "../Library/Library_Logic.vue";
import type { ReaderLogic } from "../Reader/Reader_Logic.vue";

const WORK = {
    id: "work-1",
    title: "오디세이",
    library_category: "고전문학",
    library_description: "오디세우스의 십 년 귀향",
    duration_seconds: 700,
    audio_url: "https://example.com/1.mp3",
    sentences_url: null,
    part_count: 24,
} as LibraryItem;

const readerLogic = {} as ReaderLogic;

function setSearch(search: string) {
    window.history.replaceState({}, "", `/${search}`);
}

describe("서점 작품 공유 링크", () => {
    beforeEach(() => {
        setActivePinia(createPinia());
        const state = useLibraryState();
        state.items.value = [];
        state.detailItem.value = null;
        state.detailParts.value = [];
        state.isDetailOpen.value = false;
        setSearch("");
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it("링크로 들어오면 그 작품 상세가 열린다", async () => {
        setSearch("?library=work-1");
        vi.stubGlobal("fetch", vi.fn(async () => ({
            ok: true,
            json: async () => ({ ...WORK, parts: [{ id: "p1", part_number: 1, part_title: "제1권" }] }),
        })));
        const state = useLibraryState();
        const logic = useLibraryLogic(state, readerLogic);

        const opened = await logic.checkLibraryLink();

        expect(opened).toBe(true);
        expect(state.isDetailOpen.value).toBe(true);
        expect(state.detailItem.value?.id).toBe("work-1");
        // 상세 응답이 이미 부를 들고 있다. 한 번 더 받지 않는다.
        expect(state.detailParts.value).toHaveLength(1);
        expect((globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls).toHaveLength(1);
    });

    it("주소에서 파라미터를 지운다", async () => {
        // 남겨 두면 새로고침할 때마다 상세가 다시 열리고, 닫아도 뒤로 가기로
        // 같은 화면이 또 뜬다.
        setSearch("?library=work-1");
        vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => WORK })));
        const logic = useLibraryLogic(useLibraryState(), readerLogic);

        await logic.checkLibraryLink();

        expect(window.location.search).toBe("");
    });

    it("파라미터가 없으면 아무 일도 하지 않는다", async () => {
        const fetchSpy = vi.fn();
        vi.stubGlobal("fetch", fetchSpy);
        const state = useLibraryState();
        const logic = useLibraryLogic(state, readerLogic);

        expect(await logic.checkLibraryLink()).toBe(false);
        expect(state.isDetailOpen.value).toBe(false);
        expect(fetchSpy).not.toHaveBeenCalled();
    });

    it("이미 목록에 있으면 다시 받지 않는다", async () => {
        setSearch("?library=work-1");
        const fetchSpy = vi.fn(async () => ({ ok: true, json: async () => ({ parts: [] }) }));
        vi.stubGlobal("fetch", fetchSpy);
        const state = useLibraryState();
        state.items.value = [WORK];
        const logic = useLibraryLogic(state, readerLogic);

        expect(await logic.checkLibraryLink()).toBe(true);
        expect(state.detailItem.value?.id).toBe("work-1");
        // 시리즈라 목차는 받아야 하지만, 작품 자체를 다시 받지는 않는다.
        expect(fetchSpy.mock.calls.length).toBeLessThanOrEqual(1);
    });

    it("공개 전이거나 없는 작품이면 상세를 열지 않는다", async () => {
        // 링크를 준 사람은 볼 수 있어도 받은 사람은 못 볼 수 있다
        // (review 상태이거나 내려간 작품).
        setSearch("?library=사라진-작품");
        vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 404, json: async () => ({}) })));
        const state = useLibraryState();
        const logic = useLibraryLogic(state, readerLogic);

        expect(await logic.checkLibraryLink()).toBe(false);
        expect(state.isDetailOpen.value).toBe(false);
    });

    it("공유 주소는 이 링크가 읽는 형식과 같다", async () => {
        // 만드는 쪽과 읽는 쪽이 어긋나면 링크가 조용히 아무 일도 하지 않는다.
        const shared: { url?: string } = {};
        vi.stubGlobal("navigator", {
            share: vi.fn(async (data: { url: string }) => { shared.url = data.url; }),
        });
        const logic = useLibraryLogic(useLibraryState(), readerLogic);

        await logic.share(WORK);

        expect(shared.url).toBeDefined();
        expect(new URL(shared.url!).searchParams.get("library")).toBe("work-1");
    });
});
