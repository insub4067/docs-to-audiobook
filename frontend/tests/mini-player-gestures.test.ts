import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { describe, it, expect, beforeEach, vi } from "vitest";

import MiniPlayerView from "../components/MiniPlayer/MiniPlayer_View.vue";
import { useReaderState } from "../Reader/Reader_State.vue";
import { useAudioListState } from "../components/Library/AudioList_State.vue";
import { useNewsState } from "../components/News/News_State.vue";
import type { ReaderLogic } from "../Reader/Reader_Logic.vue";

const NEWS = [
    { id: "n1", title: "첫 기사", news_category: null, news_source: null, created_at: "", audio_url: "blob:1", sentences_url: null, duration_seconds: 60 },
    { id: "n2", title: "둘째 기사", news_category: null, news_source: null, created_at: "", audio_url: "blob:2", sentences_url: null, duration_seconds: 60 },
    { id: "n3", title: "셋째 기사", news_category: null, news_source: null, created_at: "", audio_url: "blob:3", sentences_url: null, duration_seconds: 60 },
];

let logic: ReaderLogic;

function setup(queueIndex: number) {
    const readerState = useReaderState();
    readerState.title.value = "둘째 기사";
    readerState.isOpen.value = false;
    readerState.sharedPlaylistKind.value = "news";
    readerState.durationSeconds.value = 60;

    const newsState = useNewsState();
    newsState.items.value = [...NEWS];
    newsState.queueIndex.value = queueIndex;
    // 목록의 서명 URL은 1시간이면 만료돼서, 재생 직전에 오래됐으면 다시
    // 받는다(services/signedUrls.ts). 실제로는 loadNews()가 이 값을 채우므로
    // "목록은 있는데 언제 받았는지 모른다"는 상태는 프로덕션에 없다.
    newsState.fetchedAt.value = Date.now();

    const wrapper = mount(MiniPlayerView, {
        props: { state: readerState, logic, audioListState: useAudioListState() },
    });
    return { wrapper, readerState };
}

/** 포인터로 미니 플레이어를 쓸어 넘긴다. */
async function swipe(wrapper: ReturnType<typeof setup>["wrapper"], dx: number, dy: number) {
    const root = wrapper.find(".mini-player");
    await root.trigger("pointerdown", { clientX: 100, clientY: 100 });
    await root.trigger("pointermove", { clientX: 100 + dx, clientY: 100 + dy });
    await root.trigger("pointerup", { clientX: 100 + dx, clientY: 100 + dy });
}

beforeEach(() => {
    setActivePinia(createPinia());
    localStorage.clear();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ news: [] }) }));
    logic = {
        reopenReader: vi.fn(),
        dismissMiniPlayer: vi.fn(),
        togglePlayPause: vi.fn(),
        seekTo: vi.fn(),
        open: vi.fn(),
        openSharedReaderMode: vi.fn(),
    } as unknown as ReaderLogic;
});

describe("미니 플레이어 스와이프", () => {
    it("아래로 쓸어내리면 미니 플레이어를 내린다", async () => {
        const { wrapper } = setup(1);

        await swipe(wrapper, 0, 90);

        expect(logic.dismissMiniPlayer).toHaveBeenCalled();
        expect(logic.reopenReader).not.toHaveBeenCalled();
    });

    it("왼쪽으로 쓸면 재생목록 다음 항목으로 간다", async () => {
        const { wrapper } = setup(1);

        await swipe(wrapper, -90, 0);

        expect(logic.openSharedReaderMode).toHaveBeenCalled();
        expect((logic.openSharedReaderMode as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe("셋째 기사");
    });

    it("오른쪽으로 쓸면 이전 항목으로 간다", async () => {
        const { wrapper } = setup(1);

        await swipe(wrapper, 90, 0);

        expect((logic.openSharedReaderMode as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe("첫 기사");
    });

    it("항목을 넘겨도 읽기 화면을 펼치지 않는다", async () => {
        // 유튜브 뮤직처럼 미니 플레이어 안에서만 넘어가야 한다.
        // openSharedReaderMode가 무조건 isOpen을 켜고 있어서 넘길 때마다
        // 전체 화면이 떴다.
        const { wrapper } = setup(1);

        await swipe(wrapper, -90, 0);

        const options = (logic.openSharedReaderMode as ReturnType<typeof vi.fn>).mock.calls[0][3];
        expect(options.openReaderUI).toBe(false);
    });

    it("마지막 항목에서 왼쪽으로 쓸어도 넘어가지 않는다", async () => {
        const { wrapper } = setup(2);

        await swipe(wrapper, -90, 0);

        expect(logic.openSharedReaderMode).not.toHaveBeenCalled();
    });

    it("조금만 움직이면 아무 일도 하지 않는다", async () => {
        // 손가락이 살짝 흔들린 것으로 재생목록이 넘어가면 안 된다.
        const { wrapper } = setup(1);

        await swipe(wrapper, -20, 0);

        expect(logic.openSharedReaderMode).not.toHaveBeenCalled();
        expect(logic.dismissMiniPlayer).not.toHaveBeenCalled();
    });

    it("위로는 따라가지 않는다", async () => {
        const { wrapper } = setup(1);

        await swipe(wrapper, 0, -90);

        expect(logic.dismissMiniPlayer).not.toHaveBeenCalled();
    });

    it("스와이프로 끝난 제스처는 읽기 화면을 열지 않는다", async () => {
        // 브라우저는 스와이프 뒤에도 click을 보낸다. 그대로 두면 넘긴 직후
        // 리더가 열려 버린다.
        const { wrapper } = setup(1);

        await swipe(wrapper, -90, 0);
        await wrapper.find(".mini-player").trigger("click");

        expect(logic.reopenReader).not.toHaveBeenCalled();
    });

    it("그냥 누르면 읽기 화면을 연다", async () => {
        const { wrapper } = setup(1);

        await wrapper.find(".mini-player").trigger("click");

        expect(logic.reopenReader).toHaveBeenCalled();
    });

    it("진행 바에서 시작한 제스처는 재생목록을 넘기지 않는다", async () => {
        // 진행 바를 끌었을 뿐인데 다음 기사로 넘어가면 안 된다.
        const { wrapper } = setup(1);
        const bar = wrapper.find(".mini-player-progress-bar");

        await bar.trigger("pointerdown", { clientX: 100, clientY: 100, pointerId: 1 });
        await bar.trigger("pointermove", { clientX: 10, clientY: 100, pointerId: 1 });
        await bar.trigger("pointerup", { clientX: 10, clientY: 100, pointerId: 1 });

        expect(logic.openSharedReaderMode).not.toHaveBeenCalled();
        expect(logic.dismissMiniPlayer).not.toHaveBeenCalled();
    });
});
