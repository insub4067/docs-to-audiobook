import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { describe, it, expect, beforeEach, vi } from "vitest";

import NewsListSheetView from "../components/News/NewsListSheet_View.vue";
import { useNewsState } from "../components/News/News_State.vue";
import type { ReaderLogic } from "../Reader/Reader_Logic.vue";
import type { NewsItem } from "../components/News/News_State.vue";

// 목록에서 지금 듣고 있는 것이 어느 것인지 보이지 않아, 어디까지 왔는지
// 알 수 없었다. 특히 "전체 듣기"로 열 개를 이어 들을 때 그렇다.

function newsItem(id: string, title: string): NewsItem {
    return {
        id, title, audio_url: `blob:${id}`, sentences_url: "",
        news_category: "투자", news_source: "테스트",
        created_at: new Date().toISOString(), duration_seconds: 60,
    } as NewsItem;
}

const ITEMS = [newsItem("1", "기사A"), newsItem("2", "기사B"), newsItem("3", "기사C")];

function setup(queueIndex: number) {
    const state = useNewsState();
    state.items.value = [...ITEMS];
    state.queueIndex.value = queueIndex;
    state.isListOpen.value = true;
    // 로딩 자리표시자가 아니라 실제 목록을 그리게 한다.
    state.loaded.value = true;
    state.prefetchedNext.value = null;
    state.fetchedAt.value = Date.now();

    const wrapper = mount(NewsListSheetView, {
        props: { logic: {} as ReaderLogic },
    });
    return { state, wrapper, rows: wrapper.findAll(".audio-item-news") };
}

beforeEach(() => {
    setActivePinia(createPinia());
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
});

describe("재생 중인 항목 표시", () => {
    it("듣고 있는 기사에만 표시가 붙는다", () => {
        const { rows } = setup(1);

        expect(rows.map((r) => r.classes().includes("is-playing"))).toEqual([false, true, false]);
    });

    it("표시는 색만이 아니라 움직이는 막대로도 알린다", () => {
        // 색만 쓰면 색각 이상이나 강한 햇빛 아래에서 놓친다.
        const { rows } = setup(0);

        expect(rows[0].find(".now-playing-bars").exists()).toBe(true);
        expect(rows[1].find(".now-playing-bars").exists()).toBe(false);
    });

    it("보조 기술에도 현재 항목임을 알린다", () => {
        const { rows } = setup(2);

        expect(rows[2].attributes("aria-current")).toBe("true");
        expect(rows[0].attributes("aria-current")).toBeUndefined();
    });

    it("아무것도 재생 중이 아니면 어디에도 표시하지 않는다", () => {
        const { rows } = setup(-1);

        expect(rows.some((r) => r.classes().includes("is-playing"))).toBe(false);
    });

    it("재생이 다음 기사로 넘어가면 표시도 따라간다", async () => {
        const { state, wrapper } = setup(0);

        state.queueIndex.value = 2;
        await wrapper.vm.$nextTick();

        const rows = wrapper.findAll(".audio-item-news");
        expect(rows.map((r) => r.classes().includes("is-playing"))).toEqual([false, false, true]);
    });

    it("lucide 아이콘은 토글하지 않는다", () => {
        // ⚠️ lucide가 <i data-lucide>를 <svg>로 갈아치우므로, 이 아이콘을
        // v-if/v-show로 켜고 끄면 Vue의 vnode가 사라진 <i>를 가리켜 크래시가
        // 난다(프로필 화면에서 실제로 겪었다). 재생 중이든 아니든 모든 행에
        // 아이콘이 그대로 있어야 한다.
        const { rows } = setup(1);

        expect(rows.every((r) => r.find('[data-lucide="play-circle"]').exists())).toBe(true);
    });
});
