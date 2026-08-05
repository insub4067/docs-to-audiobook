import { describe, it, expect, beforeEach, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import { useNewsState } from "../components/News/News_State.vue";
import { useNewsLogic } from "../components/News/News_Logic.vue";
import type { ReaderLogic } from "../Reader/Reader_Logic.vue";
import type { NewsItem } from "../components/News/News_State.vue";

function newsItem(id: string, title: string): NewsItem {
    return {
        id,
        title,
        audio_url: `blob:${id}`,
        sentences_url: "",
        news_category: "투자",
        news_source: "테스트",
        created_at: new Date().toISOString(),
        duration_seconds: 60,
    } as NewsItem;
}

beforeEach(() => {
    setActivePinia(createPinia());
});

function setup(items: NewsItem[]) {
    const state = useNewsState();
    state.items.value = items;
    // openSharedReaderMode에 넘어온 onEnded를 붙잡아 "오디오가 끝났다"를
    // 직접 흉내낸다.
    const opened: string[] = [];
    let lastOnEnded: ((mode: string) => void) | undefined;
    const readerLogic = {
        openSharedReaderMode: vi.fn((title: string, _s: unknown, _u: string, options?: { onEnded?: (m: string) => void }) => {
            opened.push(title);
            lastOnEnded = options?.onEnded;
        }),
    } as unknown as ReaderLogic;

    const logic = useNewsLogic(state, readerLogic);
    return { state, logic, opened, fireEnded: (mode: string) => lastOnEnded?.(mode) };
}

// 회귀: "전체 반복"인데 기사 하나만 계속 되풀이됐다. 전체 반복은 재생목록
// 전체를 반복하라는 뜻이다.
describe("경제 뉴스 전체 듣기 + 반복", () => {
    const items = [newsItem("1", "기사A"), newsItem("2", "기사B"), newsItem("3", "기사C")];

    it("전체 반복이면 마지막 기사 뒤에 첫 기사로 돌아간다", async () => {
        const { logic, opened, fireEnded } = setup(items);

        await logic.playAll();
        expect(opened).toEqual(["기사A"]);

        fireEnded("all");
        await vi.waitFor(() => expect(opened).toEqual(["기사A", "기사B"]));

        fireEnded("all");
        await vi.waitFor(() => expect(opened).toEqual(["기사A", "기사B", "기사C"]));

        // 마지막 기사가 끝나면 처음으로 되돌아간다.
        fireEnded("all");
        await vi.waitFor(() => expect(opened).toEqual(["기사A", "기사B", "기사C", "기사A"]));
    });

    it("반복이 꺼져 있으면 마지막 기사 뒤에 멈춘다", async () => {
        const { state, logic, opened, fireEnded } = setup(items);

        await logic.playAll();
        fireEnded("off");
        await vi.waitFor(() => expect(opened).toHaveLength(2));
        fireEnded("off");
        await vi.waitFor(() => expect(opened).toHaveLength(3));

        fireEnded("off");
        await vi.waitFor(() => expect(state.queueIndex.value).toBe(-1));
        expect(opened).toHaveLength(3);
    });

    it("기사가 하나뿐이어도 전체 반복이면 계속 다시 재생한다", async () => {
        const { logic, opened, fireEnded } = setup([newsItem("1", "유일한 기사")]);

        await logic.playAll();
        fireEnded("all");
        await vi.waitFor(() => expect(opened).toEqual(["유일한 기사", "유일한 기사"]));
    });
});
