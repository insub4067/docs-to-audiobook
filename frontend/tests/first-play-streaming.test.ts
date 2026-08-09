import { describe, it, expect, beforeEach, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import { useReaderState } from "../Reader/Reader_State.vue";
import { useReaderLogic } from "../Reader/Reader_Logic.vue";
import { useReaderControlsState } from "../Reader/ReaderControls/ReaderControls_State.vue";
import { useReaderControlsLogic } from "../Reader/ReaderControls/ReaderControls_Logic.vue";
import type { AudioListLogic } from "../components/Library/AudioList_Logic.vue";
import type { AudiobookRecord } from "../services/indexedDb";

// 회귀: 서버에서 생성한 오디오북의 첫 재생이 오래 걸렸다. 동기화로 들어온
// 항목은 본체 없이 URL만 갖는데(cloudOnly), 재생을 누르면 MP3 전체를
// arrayBuffer()로 다 받은 뒤에야 리더가 열렸다. 22분짜리면 20MB다.
//
// 브라우저는 MP3를 다 받지 않아도 앞부분만으로 재생을 시작한다. 본체가
// 없으면 원격 URL을 그대로 틀고, 받아 두는 일은 뒤에서 한다.

function setup() {
    const state = useReaderState();
    const controlsState = useReaderControlsState();
    const controlsLogic = useReaderControlsLogic(controlsState, state.audioEl);
    const logic = useReaderLogic(state, controlsLogic, {} as AudioListLogic);

    const el = document.createElement("audio");
    el.load = vi.fn();
    el.play = vi.fn().mockResolvedValue(undefined);
    state.audioEl.value = el;
    return { state, logic, el };
}

beforeEach(() => {
    setActivePinia(createPinia());
    localStorage.clear();
});

describe("첫 재생 — 본체 없이 스트리밍", () => {
    it("⚠️ 본체가 없으면 원격 URL을 그대로 src로 쓴다", () => {
        // 이게 이번 수정의 핵심이다. blob을 만들려면 전체를 받아야 한다.
        const { state, logic, el } = setup();
        const cloudOnly = {
            id: "a1", title: "적십자 지침.pdf", timestamp: 0,
            audioData: null, audioUrl: "https://storage/signed/a1.mp3", sentences: [],
        } as unknown as AudiobookRecord;

        logic.open(cloudOnly, { autoplay: false });

        expect(el.src).toBe("https://storage/signed/a1.mp3");
        expect(state.currentAudioObject.value?.id).toBe("a1");
    });

    it("본체가 있으면 예전처럼 blob으로 튼다", () => {
        // 로컬 생성분은 오프라인에서도 되어야 하므로 blob 경로가 그대로 남아야 한다.
        const { logic, el } = setup();
        const local = {
            id: "a2", title: "로컬.pdf", timestamp: 0,
            audioData: new Blob(["audio"], { type: "audio/mpeg" }), sentences: [],
        } as unknown as AudiobookRecord;

        logic.open(local, { autoplay: false });

        expect(el.src.startsWith("blob:")).toBe(true);
    });

    it("스트리밍 항목도 목록에서 재생 중으로 표시된다", async () => {
        const { logic } = setup();
        const { nowPlayingId } = await import("../services/nowPlaying");

        logic.open({
            id: "a3", title: "원격.pdf", timestamp: 0,
            audioData: null, audioUrl: "https://storage/signed/a3.mp3", sentences: [],
        } as unknown as AudiobookRecord, { autoplay: false });

        expect(nowPlayingId.value).toBe("a3");
        nowPlayingId.value = null;
    });

    it("원격 URL은 revoke 대상이 아니다", () => {
        // 우리가 만든 objectURL이 아니라서 revoke하면 안 된다. 다음 문서를
        // 열 때 revoke가 남의 URL을 건드리면 조용히 재생이 깨진다.
        const { logic, el } = setup();
        const revoke = vi.spyOn(URL, "revokeObjectURL");

        logic.open({
            id: "a4", title: "원격.pdf", timestamp: 0,
            audioData: null, audioUrl: "https://storage/signed/a4.mp3", sentences: [],
        } as unknown as AudiobookRecord, { autoplay: false });
        logic.open({
            id: "a5", title: "다음.pdf", timestamp: 0,
            audioData: null, audioUrl: "https://storage/signed/a5.mp3", sentences: [],
        } as unknown as AudiobookRecord, { autoplay: false });

        expect(revoke).not.toHaveBeenCalledWith("https://storage/signed/a4.mp3");
        expect(el.src).toBe("https://storage/signed/a5.mp3");
        revoke.mockRestore();
    });
});
