import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

import LibraryView from "../Library/Library_View.vue";
import { useLibraryState, type LibraryItem } from "../Library/Library_State.vue";
import type { ReaderLogic } from "../Reader/Reader_Logic.vue";

function work(overrides: Partial<LibraryItem> = {}): LibraryItem {
    return {
        id: "book-1",
        title: "도덕경",
        library_category: "철학·사상",
        library_edition: null,
        library_translator: null,
        library_source: null,
        library_rights: null,
        library_description: null,
        library_chapter_count: 81,
        duration_seconds: 3600,
        created_at: "2026-08-01",
        audio_url: "blob:fake",
        sentences_url: null,
        ...overrides,
    };
}

const WORKS = [
    work({ id: "a", title: "도덕경", duration_seconds: 3600, library_translator: "오강남" }),
    work({ id: "b", title: "금강경", duration_seconds: 600, library_category: "종교·경전", library_source: "한글대장경" }),
    work({ id: "c", title: "논어", duration_seconds: 7200, library_description: "공자의 가르침" }),
];

let state: ReturnType<typeof useLibraryState>;

function mountLibrary() {
    return mount(LibraryView, { props: { logic: {} as ReaderLogic } });
}

function titlesIn(wrapper: ReturnType<typeof mountLibrary>): string[] {
    return wrapper.findAll(".audio-title").map((el) => el.text());
}

beforeEach(() => {
    setActivePinia(createPinia());
    localStorage.clear();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ library: [], positions: {} }) }));
    state = useLibraryState();
    state.items.value = [...WORKS];
    state.loaded.value = true;
    state.searchQuery.value = "";
    state.sortKey.value = "recent";
    state.activeCategory.value = null;
    state.playbackSeconds.value = {};
});

afterEach(() => {
    vi.unstubAllGlobals();
});

describe("라이브러리 검색", () => {
    it("제목으로 찾는다", async () => {
        const wrapper = mountLibrary();
        state.searchQuery.value = "금강";
        await wrapper.vm.$nextTick();

        expect(titlesIn(wrapper)).toEqual(["금강경"]);
    });

    it("번역자·출처·설명으로도 찾는다", async () => {
        // 같은 원전이라도 판본이 여럿이면 제목만으로는 고를 수 없다.
        const wrapper = mountLibrary();

        for (const [query, expected] of [["오강남", "도덕경"], ["한글대장경", "금강경"], ["공자", "논어"]] as const) {
            state.searchQuery.value = query;
            await wrapper.vm.$nextTick();
            expect(titlesIn(wrapper)).toEqual([expected]);
        }
    });

    it("낱말을 띄어 쓰면 모두 포함한 작품만 남는다", async () => {
        const wrapper = mountLibrary();
        state.searchQuery.value = "도덕경 오강남";
        await wrapper.vm.$nextTick();
        expect(titlesIn(wrapper)).toEqual(["도덕경"]);

        state.searchQuery.value = "도덕경 한글대장경";
        await wrapper.vm.$nextTick();
        expect(titlesIn(wrapper)).toEqual([]);
    });

    it("검색 결과가 없으면 등록된 작품이 없다고 하지 않는다", async () => {
        const wrapper = mountLibrary();
        state.searchQuery.value = "없는작품";
        await wrapper.vm.$nextTick();

        expect(wrapper.text()).toContain("검색 결과가 없어요.");
        expect(wrapper.text()).not.toContain("아직 등록된 작품이 없어요.");
    });
});

describe("라이브러리 정렬", () => {
    it("기본은 서버가 준 순서를 유지한다", () => {
        const wrapper = mountLibrary();

        expect(titlesIn(wrapper)).toEqual(["도덕경", "금강경", "논어"]);
    });

    it("짧은 작품순 / 긴 작품순", async () => {
        const wrapper = mountLibrary();

        state.sortKey.value = "duration-asc";
        await wrapper.vm.$nextTick();
        expect(titlesIn(wrapper)).toEqual(["금강경", "도덕경", "논어"]);

        state.sortKey.value = "duration-desc";
        await wrapper.vm.$nextTick();
        expect(titlesIn(wrapper)).toEqual(["논어", "도덕경", "금강경"]);
    });

    it("'듣는 중'은 듣던 작품을 위로, 다 들은 작품을 아래로 보낸다", async () => {
        const wrapper = mountLibrary();
        state.playbackSeconds.value = { c: 1800, b: 595 }; // 논어 25%, 금강경 99%
        state.sortKey.value = "listening";
        await wrapper.vm.$nextTick();

        expect(titlesIn(wrapper)).toEqual(["논어", "도덕경", "금강경"]);
    });

    it("정렬이 원본 목록의 순서를 망가뜨리지 않는다", async () => {
        const wrapper = mountLibrary();
        state.sortKey.value = "duration-asc";
        await wrapper.vm.$nextTick();

        expect(state.items.value.map((item) => item.title)).toEqual(["도덕경", "금강경", "논어"]);
    });
});
