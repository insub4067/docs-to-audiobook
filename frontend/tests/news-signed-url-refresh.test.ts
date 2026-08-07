import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import { useNewsState } from "../components/News/News_State.vue";
import { useNewsLogic } from "../components/News/News_Logic.vue";
import type { ReaderLogic } from "../Reader/Reader_Logic.vue";

// 목록의 audio_url/sentences_url은 1시간짜리 서명 URL이다. 홈의 경제 뉴스는
// 앱을 켤 때 한 번만 목록을 받아 왔는데, PWA는 며칠씩 열려 있다. 한 시간이
// 지난 뒤 기사를 누르면 오디오도 문장도 404가 나서 빈 본문에 00:00만 뜨고
// "공유 오디오를 불러올 수 없습니다"가 떴다. 실제로 그렇게 깨졌다.
const HOUR = 60 * 60 * 1000;

function newsItem(id: string, token: string) {
    return {
        id, title: `기사 ${id}`, news_category: null, news_source: null, created_at: "",
        audio_url: `https://storage/${id}.mp3?token=${token}`,
        sentences_url: `https://storage/${id}.json?token=${token}`,
        duration_seconds: 60,
    };
}

let readerLogic: ReaderLogic;
let listResponses: ReturnType<typeof newsItem>[][];
let listFetchCount: number;

function setup() {
    const state = useNewsState();
    return { state, logic: useNewsLogic(state, readerLogic) };
}

beforeEach(() => {
    setActivePinia(createPinia());
    localStorage.clear();
    listFetchCount = 0;
    listResponses = [];
    readerLogic = { openSharedReaderMode: vi.fn() } as unknown as ReaderLogic;

    // News_State는 모듈 싱글턴이라(홈 카드와 목록 시트가 같은 큐를 봐야 한다)
    // 앞 테스트가 채운 값이 다음 테스트로 새어 나간다. 매번 초기화한다.
    const shared = useNewsState();
    shared.items.value = [];
    shared.loaded.value = false;
    shared.fetchedAt.value = 0;
    shared.queueIndex.value = -1;
    shared.isContinuous.value = false;

    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
        if (url === "/api/news") {
            const body = listResponses[Math.min(listFetchCount, listResponses.length - 1)];
            listFetchCount += 1;
            return { ok: true, json: async () => ({ news: body }) };
        }
        return { ok: true, json: async () => [] };
    }));
});

afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
});

function openedAudioUrl(): string {
    const calls = (readerLogic.openSharedReaderMode as ReturnType<typeof vi.fn>).mock.calls;
    return calls[calls.length - 1][2];
}

describe("서명 URL 만료 방지", () => {
    it("목록이 아직 신선하면 다시 받지 않는다", async () => {
        listResponses = [[newsItem("a", "fresh")]];
        const { state, logic } = setup();
        await logic.loadNews();

        await logic.openNewsItem(state.items.value[0]);

        expect(listFetchCount).toBe(1);
        expect(openedAudioUrl()).toContain("token=fresh");
    });

    it("한 시간 가까이 지났으면 재생 직전에 목록을 다시 받는다", async () => {
        listResponses = [[newsItem("a", "old")], [newsItem("a", "new")]];
        const { state, logic } = setup();
        await logic.loadNews();
        const stale = state.items.value[0];

        vi.useFakeTimers();
        vi.setSystemTime(Date.now() + 31 * 60 * 1000);
        await logic.openNewsItem(stale);

        expect(listFetchCount).toBe(2);
        // 죽은 URL로 열면 빈 본문에 00:00만 뜬다.
        expect(openedAudioUrl()).toContain("token=new");
    });

    it("유효시간의 절반이 되기 전에는 갱신하지 않는다", async () => {
        // 만료 직전에 갱신하면 재생을 누르는 순간 만료되는 창이 남는다.
        // 절반(30분)을 경계로 삼았는지 양쪽에서 확인한다.
        listResponses = [[newsItem("a", "old")], [newsItem("a", "new")]];
        const { state, logic } = setup();
        await logic.loadNews();

        vi.useFakeTimers();
        vi.setSystemTime(Date.now() + 29 * 60 * 1000);
        await logic.openNewsItem(state.items.value[0]);

        expect(listFetchCount).toBe(1);
    });

    it("갱신했더니 목록에서 사라진 기사면 재생하지 않고 알려 준다", async () => {
        // 뉴스는 매일 갈린다. 사라진 기사를 죽은 URL로 열면 사용자는
        // "오디오를 불러올 수 없습니다"만 보고 이유를 알 수 없다.
        listResponses = [[newsItem("gone", "old")], [newsItem("other", "new")]];
        const { state, logic } = setup();
        await logic.loadNews();
        const removed = state.items.value[0];

        vi.useFakeTimers();
        vi.setSystemTime(Date.now() + HOUR);
        await logic.openNewsItem(removed);

        expect(readerLogic.openSharedReaderMode).not.toHaveBeenCalled();
    });

    it("목록을 받을 때마다 받은 시각을 기록한다", async () => {
        listResponses = [[newsItem("a", "t")]];
        const { state, logic } = setup();

        expect(state.fetchedAt.value).toBe(0);
        await logic.loadNews();

        expect(state.fetchedAt.value).toBeGreaterThan(0);
    });
});
