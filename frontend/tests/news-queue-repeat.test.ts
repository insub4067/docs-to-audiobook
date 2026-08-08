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
    // News_State는 모듈 싱글턴이라(홈 카드와 목록 시트가 같은 큐를 봐야 한다)
    // 앞 테스트가 남긴 값이 그대로 넘어온다. 특히 미리 받아 둔 다음 기사는
    // 목록이 바뀌어도 id가 우연히 같으면 잘못 쓰인다 — 매번 비운다.
    state.items.value = items;
    state.prefetchedNext.value = null;
    state.queueIndex.value = -1;
    state.isContinuous.value = false;
    state.fetchedAt.value = Date.now();
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

// 회귀: "전체 듣기"가 아니라 목록에서 기사 하나를 눌러 들을 때도 전체
// 반복이면 목록을 순환해야 한다. 예전에는 이 경로에 큐가 없어서 그 기사만
// 되풀이됐다 — 사용자가 실제로 겪은 증상이다.
describe("목록에서 기사 하나를 눌러 들을 때", () => {
    const items = [newsItem("1", "기사A"), newsItem("2", "기사B"), newsItem("3", "기사C")];

    it("전체 반복이면 그 기사부터 목록을 순환한다", async () => {
        const { logic, opened, fireEnded } = setup(items);

        await logic.openNewsItem(items[1]);          // 가운데 기사를 탭
        expect(opened).toEqual(["기사B"]);

        fireEnded("all");
        await vi.waitFor(() => expect(opened).toEqual(["기사B", "기사C"]));

        // 목록 끝에서 처음으로 돌아간다.
        fireEnded("all");
        await vi.waitFor(() => expect(opened).toEqual(["기사B", "기사C", "기사A"]));
    });

    it("반복이 꺼져 있으면 그 기사만 듣고 끝난다", async () => {
        // 개별 재생은 자동으로 다음 기사로 넘어가지 않는다(기존 동작 유지).
        const { logic, opened, fireEnded } = setup(items);

        await logic.openNewsItem(items[0]);
        fireEnded("off");
        await new Promise((r) => setTimeout(r, 50));

        expect(opened).toEqual(["기사A"]);
    });
});

// 회귀: PWA를 벗어나면 연속 재생이 멈췄다.
//
// 예전에는 ended 안에서 서명 URL 갱신과 문장 데이터를 네트워크로 받아 온
// 뒤에야 다음 곡을 틀었다. 화면이 백그라운드면 그 사이에 실행이 지연되고,
// 새로 불러온 소스에 대한 play()는 사용자 조작과 멀어져 자동재생으로
// 취급돼 막힌다. 그래서 지금 곡을 트는 즉시 다음 것을 받아 둔다.
describe("다음 기사 선행 준비", () => {
    const items = [newsItem("1", "기사A"), newsItem("2", "기사B"), newsItem("3", "기사C")];

    it("현재 기사를 틀면 다음 기사를 미리 받아 둔다", async () => {
        const { state, logic } = setup(items);

        await logic.playAll();

        await vi.waitFor(() => expect(state.prefetchedNext.value?.id).toBe("2"));
    });

    it("목록 끝에서는 첫 기사를 미리 받아 둔다", async () => {
        // "전체 반복"이 그렇게 돌기 때문에 마지막에서도 준비할 것이 있다.
        const { state, logic } = setup(items);

        await logic.openNewsItem(items[2], 2);

        await vi.waitFor(() => expect(state.prefetchedNext.value?.id).toBe("1"));
    });

    it("준비돼 있으면 ended에서 네트워크를 타지 않고 곧바로 다음 곡을 튼다", async () => {
        // ⚠️ 이게 이 파일에서 제일 중요한 확인이다. ended와 재생 사이에
        // await가 하나라도 끼면 백그라운드에서 다음 곡이 이어지지 않는다.
        const { state, logic, opened, fireEnded } = setup(items);
        await logic.playAll();
        await vi.waitFor(() => expect(state.prefetchedNext.value?.id).toBe("2"));

        fireEnded("off");

        // await 없이, 같은 틱에 이미 열려 있어야 한다.
        expect(opened).toEqual(["기사A", "기사B"]);
    });

    it("목록이 갈리면 미리 받아 둔 것을 쓰지 않는다", async () => {
        // 뉴스는 매일 통째로 교체된다. 예전 기사를 새 목록의 다음 순서인 척
        // 틀면 안 된다.
        const { state, logic, opened, fireEnded } = setup(items);
        await logic.playAll();
        await vi.waitFor(() => expect(state.prefetchedNext.value?.id).toBe("2"));

        // 같은 자리에 다른 기사가 들어온 상황
        state.items.value = [items[0], newsItem("99", "새 기사")];
        fireEnded("off");

        await vi.waitFor(() => expect(opened).toEqual(["기사A", "새 기사"]));
    });
});
