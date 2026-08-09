import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { describe, it, expect, beforeEach, vi } from "vitest";

import NewsListSheetView from "../components/News/NewsListSheet_View.vue";
import { useNewsState } from "../components/News/News_State.vue";
import type { ReaderLogic } from "../Reader/Reader_Logic.vue";
import type { NewsItem } from "../components/News/News_State.vue";
import { nowPlayingId, setNowPlaying, setNowPlayingState } from "../services/nowPlaying";

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

/** playingIndex는 "몇 번째 기사를 듣고 있나"를 읽기 쉽게 쓴 것이고,
 *  실제 판정 기준은 id다 — 자리로 판정하면 다른 문서를 재생해도 표시가
 *  남는다(실제로 그 버그가 있었다). */
function setup(playingIndex: number) {
    const state = useNewsState();
    state.items.value = [...ITEMS];
    setNowPlaying(ITEMS[playingIndex]?.id ?? null);
    state.queueIndex.value = playingIndex;
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
        const { rows } = setup(0);

        expect(rows[0].find(".row-play-bars").exists()).toBe(true);
        expect(rows[1].find(".row-play-bars").exists()).toBe(true);
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
        const { wrapper } = setup(0);

        setNowPlaying(ITEMS[2].id);
        await wrapper.vm.$nextTick();

        const rows = wrapper.findAll(".audio-item-news");
        expect(rows.map((r) => r.classes().includes("is-playing"))).toEqual([false, false, true]);
    });

    it("⚠️ 다른 문서를 재생하면 뉴스 표시가 사라진다", () => {
        // 실제로 겪은 버그다. 뉴스 목록만 queueIndex(뉴스 큐 안의 자리)로
        // 판정하고 있어서, 개인 오디오북을 듣는 중에도 마지막에 듣던 기사에
        // "재생 중"이 그대로 남아 있었다. 판정 기준을 id 하나로 모았다.
        const { wrapper } = setup(0);
        expect(wrapper.findAll(".audio-item-news")[0].classes()).toContain("is-playing");

        // 뉴스 큐 위치는 그대로 두고, 재생 중인 것만 다른 문서로 바꾼다.
        setNowPlaying("개인-오디오북-id");

        return wrapper.vm.$nextTick().then(() => {
            const rows = wrapper.findAll(".audio-item-news");
            expect(rows.some((r) => r.classes().includes("is-playing"))).toBe(false);
            wrapper.unmount();
        });
    });

    it("아무것도 재생 중이 아니면 큐 위치가 남아 있어도 표시하지 않는다", async () => {
        const { state, wrapper } = setup(1);
        expect(state.queueIndex.value).toBe(1);

        setNowPlaying(null);
        await wrapper.vm.$nextTick();

        expect(wrapper.findAll(".audio-item-news").some((r) => r.classes().includes("is-playing"))).toBe(false);
        wrapper.unmount();
    });

    it("일시정지하면 is-paused 클래스가 추가된다", async () => {
        const { wrapper, rows } = setup(1);

        expect(rows[1].classes()).toContain("is-playing");
        expect(rows[1].classes()).not.toContain("is-paused");

        setNowPlayingState("paused");
        await wrapper.vm.$nextTick();

        const updated = wrapper.findAll(".audio-item-news");
        expect(updated[1].classes()).toContain("is-playing");
        expect(updated[1].classes()).toContain("is-paused");
        wrapper.unmount();
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

// "모든 셀에 적용" — 재생목록 시트뿐 아니라 홈·내 파일·서점 목록에서도
// 지금 듣고 있는 항목이 보여야 한다. 목록마다 신호가 다르면 매번 새로 배운다.
describe("보관함 목록에도 같은 표시", () => {
    it("지금 듣는 오디오북 행에만 표시가 붙는다", async () => {
        const { mount } = await import("@vue/test-utils");
        const { nowPlayingId, setNowPlaying } = await import("../services/nowPlaying");
        const AudioListItemView = (await import("../components/Library/AudioListItem_View.vue")).default;

        const audio = { id: "a1", title: "데미안.pdf", timestamp: 0 };
        setNowPlaying("a1");
        const playing = mount(AudioListItemView, {
            props: { audio: audio as never, logic: {} as never },
        });
        setNowPlaying("다른-것");
        const idle = mount(AudioListItemView, {
            props: { audio: audio as never, logic: {} as never },
        });

        expect(playing.find(".audio-item").classes()).toContain("is-playing");
        expect(playing.find(".row-play-bars").exists()).toBe(true);
        expect(idle.find(".audio-item").classes()).not.toContain("is-playing");
        nowPlayingId.value = null;
        playing.unmount();
        idle.unmount();
    });

    it("재생이 바뀌면 표시도 따라간다", async () => {
        const { mount } = await import("@vue/test-utils");
        const { nowPlayingId, setNowPlaying } = await import("../services/nowPlaying");
        const AudioListItemView = (await import("../components/Library/AudioListItem_View.vue")).default;

        nowPlayingId.value = null;
        const wrapper = mount(AudioListItemView, {
            props: { audio: { id: "a1", title: "데미안.pdf", timestamp: 0 } as never, logic: {} as never },
        });
        expect(wrapper.find(".audio-item").classes()).not.toContain("is-playing");

        setNowPlaying("a1");
        await wrapper.vm.$nextTick();

        expect(wrapper.find(".audio-item").classes()).toContain("is-playing");
        nowPlayingId.value = null;
        wrapper.unmount();
    });
});
