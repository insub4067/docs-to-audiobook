import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { describe, it, expect, beforeEach, vi } from "vitest";

import TodayNewsView from "../components/News/TodayNews_View.vue";
import { useNewsState } from "../components/News/News_State.vue";
import type { ReaderLogic } from "../Reader/Reader_Logic.vue";

// 예전에는 목록이 도착할 때까지 카드가 통째로 없다가(v-if="topItem") 갑자기
// 나타났다. 홈에 들어오면 그 아래 내용이 밀리면서 뉴스 카드가 끼어드는
// 셈이라, 누르려던 것이 움직인다.
function newsItem(id: string) {
    return {
        id, title: `기사 ${id}`, news_category: "국제", news_source: "Reuters",
        created_at: new Date().toISOString(),
        audio_url: "blob:x", sentences_url: null, duration_seconds: 60,
    };
}

let readerLogic: ReaderLogic;

function resetNewsState() {
    const state = useNewsState();
    state.items.value = [];
    state.loaded.value = false;
    state.fetchedAt.value = 0;
    return state;
}

/** loadNews가 끝나지 않게 잡아 두고, 원할 때 응답을 준다. */
function pendingFetch() {
    let release!: (items: ReturnType<typeof newsItem>[]) => void;
    const pending = new Promise<ReturnType<typeof newsItem>[]>((resolve) => { release = resolve; });
    vi.stubGlobal("fetch", vi.fn(async () => ({
        ok: true,
        json: async () => ({ news: await pending }),
    })));
    return release;
}

beforeEach(() => {
    setActivePinia(createPinia());
    readerLogic = {} as ReaderLogic;
});

describe("경제 뉴스 로딩 자리표시자", () => {
    it("불러오는 동안 카드를 감추지 않고 자리표시자를 그린다", () => {
        resetNewsState();
        pendingFetch();

        const wrapper = mount(TodayNewsView, { props: { logic: readerLogic } });

        expect(wrapper.find(".library-section").exists()).toBe(true);
        expect(wrapper.find(".list-row-placeholder").exists()).toBe(true);
        wrapper.unmount();
    });

    it("자리표시자는 실제 행과 같은 골격을 갖는다", () => {
        // 골격이 다르면 내용이 도착하는 순간 높이가 바뀌어, 자리를 잡아 둔
        // 의미가 없어진다.
        resetNewsState();
        pendingFetch();

        const wrapper = mount(TodayNewsView, { props: { logic: readerLogic } });
        const placeholder = wrapper.find(".list-row-placeholder");

        expect(placeholder.find(".redacted-icon").exists()).toBe(true);
        expect(placeholder.find(".redacted-title").exists()).toBe(true);
        expect(placeholder.find(".redacted-subtitle").exists()).toBe(true);
        wrapper.unmount();
    });

    it("자리표시자는 눌러도 아무 일이 없어야 한다", () => {
        resetNewsState();
        pendingFetch();

        const wrapper = mount(TodayNewsView, { props: { logic: readerLogic } });
        const placeholder = wrapper.find(".list-row-placeholder");

        // <button>이면 탭이 여기서 멈추고 스크린 리더도 읽는다.
        expect(placeholder.element.tagName).toBe("DIV");
        expect(placeholder.attributes("aria-hidden")).toBe("true");
        wrapper.unmount();
    });

    it("도착하면 자리표시자를 치우고 기사를 보여 준다", async () => {
        const state = resetNewsState();
        const release = pendingFetch();

        const wrapper = mount(TodayNewsView, { props: { logic: readerLogic } });
        release([newsItem("a")]);
        await vi.waitFor(() => expect(state.loaded.value).toBe(true));
        await wrapper.vm.$nextTick();

        expect(wrapper.find(".list-row-placeholder").exists()).toBe(false);
        expect(wrapper.text()).toContain("기사 a");
        wrapper.unmount();
    });

    it("다 받아 왔는데 뉴스가 없으면 카드를 감춘다", async () => {
        const state = resetNewsState();
        const release = pendingFetch();

        const wrapper = mount(TodayNewsView, { props: { logic: readerLogic } });
        release([]);
        await vi.waitFor(() => expect(state.loaded.value).toBe(true));
        await wrapper.vm.$nextTick();

        expect(wrapper.find(".library-section").exists()).toBe(false);
        wrapper.unmount();
    });

    it("자리표시자 상태에서는 더보기를 노출하지 않는다", () => {
        // 눌러 봐야 빈 시트만 열린다.
        resetNewsState();
        pendingFetch();

        const wrapper = mount(TodayNewsView, { props: { logic: readerLogic } });

        expect(wrapper.find(".news-more-btn").exists()).toBe(false);
        wrapper.unmount();
    });
});
