import { describe, it, expect, beforeEach, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import { useReaderState } from "../Reader/Reader_State.vue";
import { useReaderLogic } from "../Reader/Reader_Logic.vue";
import { useReaderControlsState } from "../Reader/ReaderControls/ReaderControls_State.vue";
import { useReaderControlsLogic } from "../Reader/ReaderControls/ReaderControls_Logic.vue";
import type { AudioListLogic } from "../components/Library/AudioList_Logic.vue";

const SENTENCES = [{ text: "첫 문장", start: 0, end: 1000 }];

function setup() {
    const readerState = useReaderState();
    const controlsState = useReaderControlsState();
    const controlsLogic = useReaderControlsLogic(controlsState, readerState.audioEl);
    const readerLogic = useReaderLogic(readerState, controlsLogic, {} as AudioListLogic);

    // jsdom의 HTMLMediaElement는 load/play가 구현돼 있지 않다.
    const el = document.createElement("audio");
    el.load = vi.fn();
    const play = vi.fn().mockResolvedValue(undefined);
    el.play = play;
    readerState.audioEl.value = el;

    return { readerState, controlsState, controlsLogic, readerLogic, el, play };
}

beforeEach(() => {
    setActivePinia(createPinia());
    localStorage.clear();
});

// 회귀: "전체 문서 반복"을 골라도 재생이 그냥 끝나 버렸다. 반복을 구현한
// ReaderControls_Logic.onEnded가 어디에도 연결돼 있지 않아 호출되지 않는
// 죽은 코드였기 때문이다(일반 오디오북·뉴스 양쪽 모두).
describe("반복 모드가 실제 audio 엘리먼트에 연결된다", () => {
    it("공유/뉴스 모드에서 반복이 꺼져 있으면 다음 항목으로 넘어간다", () => {
        const { readerLogic, el, controlsLogic } = setup();
        const onQueueEnded = vi.fn();

        controlsLogic.selectRepeatMode("off");
        readerLogic.openSharedReaderMode("뉴스1", SENTENCES, "blob:fake", {
            onEnded: onQueueEnded,
            playlistKind: "news",
        });
        el.onended?.(new Event("ended"));

        expect(onQueueEnded).toHaveBeenCalledTimes(1);
    });

    it("'전체 반복'은 재생목록을 반복하라는 뜻이므로 큐에 넘긴다", () => {
        // 한 기사만 되풀이하면 안 된다 — 다음 기사로 진행하고, 목록 끝에서
        // 처음으로 돌아갈지는 큐(News_Logic)가 판단한다.
        const { readerLogic, el, play, controlsLogic } = setup();
        const onQueueEnded = vi.fn();

        controlsLogic.selectRepeatMode("all");
        readerLogic.openSharedReaderMode("뉴스1", SENTENCES, "blob:fake", {
            onEnded: onQueueEnded,
            playlistKind: "news",
        });
        // 열 때 이미 한 번 재생을 요청한다 — 백그라운드에서도 다음 곡이
        // 이어지도록 load() 직후 같은 흐름에서 부른다. 여기서 확인하려는
        // 건 ended '이후'의 재생이므로 그 한 번은 지우고 본다.
        play.mockClear();
        el.onended?.(new Event("ended"));

        expect(onQueueEnded).toHaveBeenCalledWith("all");
        expect(play).not.toHaveBeenCalled();
    });

    it("'현재 오디오 반복'은 큐가 있어도 현재 기사만 다시 재생한다", () => {
        const { readerLogic, el, play, controlsLogic } = setup();
        const onQueueEnded = vi.fn();

        controlsLogic.selectRepeatMode("one");
        readerLogic.openSharedReaderMode("뉴스1", SENTENCES, "blob:fake", {
            onEnded: onQueueEnded,
            playlistKind: "news",
        });
        el.currentTime = 42;
        el.onended?.(new Event("ended"));

        expect(onQueueEnded).not.toHaveBeenCalled();
        expect(el.currentTime).toBe(0);
        expect(play).toHaveBeenCalled();
    });

    it("재생목록이 없으면 '전체 반복'은 그 오디오 하나를 반복한다", () => {
        // 라이브러리 작품처럼 큐가 없는 경우 — 그 오디오가 곧 "전체"다.
        const { readerLogic, el, play, controlsLogic } = setup();

        controlsLogic.selectRepeatMode("all");
        readerLogic.openSharedReaderMode("작품", SENTENCES, "blob:fake", {});
        el.currentTime = 42;
        el.onended?.(new Event("ended"));

        expect(el.currentTime).toBe(0);
        expect(play).toHaveBeenCalled();
    });

    it("반복이 꺼져 있고 큐 콜백도 없으면 아무 일도 하지 않는다", () => {
        const { readerLogic, el, play, controlsLogic } = setup();

        controlsLogic.selectRepeatMode("off");
        readerLogic.openSharedReaderMode("작품", SENTENCES, "blob:fake", {});
        // 열 때 이미 한 번 재생을 요청한다 — 백그라운드에서도 다음 곡이
        // 이어지도록 load() 직후 같은 흐름에서 부른다. 여기서 확인하려는
        // 건 ended '이후'의 재생이므로 그 한 번은 지우고 본다.
        play.mockClear();
        el.onended?.(new Event("ended"));

        expect(play).not.toHaveBeenCalled();
    });
});

// 내 파일에서 연 일반 오디오북(open())도 같은 문제가 있었다. 공유/뉴스
// 경로와 코드가 갈라져 있어 한쪽만 고치면 다른 쪽이 조용히 남는다.
describe("일반 오디오북(open)에서도 반복이 연결된다", () => {
    function localAudiobook(repeatMode: string) {
        return {
            id: "a1",
            title: "데미안.pdf",
            audioData: new Blob(["fake"], { type: "audio/mpeg" }),
            sentences: SENTENCES,
            playbackSpeed: 1,
            repeatMode,
            lastPosition: 0,
        };
    }

    it("반복이 켜져 있으면 끝났을 때 처음부터 다시 재생한다", () => {
        const { readerLogic, el, play } = setup();

        // open()은 오디오북 레코드에 저장된 repeatMode를 적용한다.
        readerLogic.open(localAudiobook("all") as never, { autoplay: false });
        el.currentTime = 42;
        el.onended?.(new Event("ended"));

        expect(el.currentTime).toBe(0);
        expect(play).toHaveBeenCalled();
    });

    it("반복이 꺼져 있으면 끝났을 때 그대로 멈춘다", () => {
        const { readerLogic, el, play } = setup();

        readerLogic.open(localAudiobook("off") as never, { autoplay: false });
        el.onended?.(new Event("ended"));

        expect(play).not.toHaveBeenCalled();
    });
});
