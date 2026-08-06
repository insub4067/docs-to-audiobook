import { describe, it, expect, beforeEach, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import { useReaderState } from "../Reader/Reader_State.vue";
import { useReaderLogic } from "../Reader/Reader_Logic.vue";
import { useReaderControlsState } from "../Reader/ReaderControls/ReaderControls_State.vue";
import { useReaderControlsLogic } from "../Reader/ReaderControls/ReaderControls_Logic.vue";
import type { AudioListLogic } from "../components/Library/AudioList_Logic.vue";

/** 3장짜리 작품. 각 장은 문장 인덱스와 시작 시각을 함께 갖는다. */
const CHAPTERS = [
    { text: "제1장", level: 1, sentIndex: 0, startMs: 0 },
    { text: "제2장", level: 1, sentIndex: 10, startMs: 60_000 },
    { text: "제3장", level: 1, sentIndex: 20, startMs: 120_000 },
];

function setup() {
    const readerState = useReaderState();
    const controlsState = useReaderControlsState();
    const controlsLogic = useReaderControlsLogic(controlsState, readerState.audioEl);
    const readerLogic = useReaderLogic(readerState, controlsLogic, {} as AudioListLogic);

    const el = document.createElement("audio");
    el.load = vi.fn();
    el.play = vi.fn().mockResolvedValue(undefined);
    readerState.audioEl.value = el;
    readerState.headings.value = [...CHAPTERS];

    return { state: readerState, logic: readerLogic, el };
}

beforeEach(() => {
    setActivePinia(createPinia());
    localStorage.clear();
});

describe("현재 장 판별", () => {
    it("현재 문장이 속한 장을 찾는다", () => {
        const { state, logic } = setup();
        state.activeIndex.value = 15;

        expect(logic.currentChapterIndex()).toBe(1);
    });

    it("장 시작 문장에 정확히 있으면 그 장이다", () => {
        const { state, logic } = setup();
        state.activeIndex.value = 10;

        expect(logic.currentChapterIndex()).toBe(1);
    });

    it("아직 재생 전이면 첫 장으로 본다", () => {
        const { state, logic } = setup();
        state.activeIndex.value = -1;

        expect(logic.currentChapterIndex()).toBe(0);
    });

    it("목차가 없으면 -1", () => {
        const { state, logic } = setup();
        state.headings.value = [];

        expect(logic.currentChapterIndex()).toBe(-1);
    });
});

describe("장 단위 이동", () => {
    it("다음 장으로 넘어간다", () => {
        const { state, logic, el } = setup();
        state.activeIndex.value = 5;

        logic.goToChapter(1);

        expect(el.currentTime).toBe(60);
    });

    it("마지막 장에서 다음을 눌러도 넘어가지 않는다", () => {
        const { state, logic, el } = setup();
        state.activeIndex.value = 25;
        el.currentTime = 130;

        logic.goToChapter(1);

        expect(el.currentTime).toBe(120);
    });

    it("장을 튼 지 얼마 안 됐으면 이전 장으로 간다", () => {
        const { state, logic, el } = setup();
        state.activeIndex.value = 15;
        el.currentTime = 61; // 2장 시작 1초 후

        logic.goToChapter(-1);

        expect(el.currentTime).toBe(0);
    });

    it("한참 들었으면 이전 장이 아니라 현재 장 처음으로 돌아간다", () => {
        // 음악 앱의 "이전 곡"과 같은 규칙 — 한 번 눌러 다시 듣기 쉬워야 한다.
        const { state, logic, el } = setup();
        state.activeIndex.value = 15;
        el.currentTime = 90; // 2장 시작 30초 후

        logic.goToChapter(-1);

        expect(el.currentTime).toBe(60);
    });

    it("첫 장에서 이전을 눌러도 음수로 가지 않는다", () => {
        const { state, logic, el } = setup();
        state.activeIndex.value = 2;
        el.currentTime = 1;

        logic.goToChapter(-1);

        expect(el.currentTime).toBe(0);
    });

    it("목차가 없으면 아무 일도 하지 않는다", () => {
        const { state, logic, el } = setup();
        state.headings.value = [];
        el.currentTime = 42;

        logic.goToChapter(1);

        expect(el.currentTime).toBe(42);
    });
});

describe("장 경계 처리", () => {
    /** ontimeupdate를 흉내 낸다. 시각을 옮기고 핸들러를 부른다. */
    function tick(el: HTMLAudioElement, seconds: number) {
        el.currentTime = seconds;
        el.ontimeupdate?.(new Event("timeupdate"));
    }

    function openWork(controlsLogic: ReturnType<typeof useReaderControlsLogic>, logic: ReturnType<typeof useReaderLogic>, state: ReturnType<typeof useReaderState>, el: HTMLAudioElement) {
        logic.openSharedReaderMode("작품", [{ text: "문장", start: 0, end: 1000 }], "blob:fake", {});
        state.headings.value = [...CHAPTERS];
        return { controlsLogic, el };
    }

    it("'현재 장 반복'은 장이 끝나면 그 장 처음으로 되돌린다", () => {
        const readerState = useReaderState();
        const controlsState = useReaderControlsState();
        const controlsLogic = useReaderControlsLogic(controlsState, readerState.audioEl);
        const logic = useReaderLogic(readerState, controlsLogic, {} as AudioListLogic);
        const el = document.createElement("audio");
        el.load = vi.fn();
        el.play = vi.fn().mockResolvedValue(undefined);
        Object.defineProperty(el, "duration", { value: 180, configurable: true });
        readerState.audioEl.value = el;
        openWork(controlsLogic, logic, readerState, el);
        controlsLogic.selectRepeatMode("chapter");

        tick(el, 70);   // 2장 안
        tick(el, 121);  // 3장으로 넘어가는 순간

        expect(el.currentTime).toBe(60); // 2장 처음
    });

    it("'이 장이 끝나면'은 장 끝에서 멈추고 스스로 해제된다", () => {
        const readerState = useReaderState();
        const controlsState = useReaderControlsState();
        const controlsLogic = useReaderControlsLogic(controlsState, readerState.audioEl);
        const logic = useReaderLogic(readerState, controlsLogic, {} as AudioListLogic);
        const el = document.createElement("audio");
        el.load = vi.fn();
        el.play = vi.fn().mockResolvedValue(undefined);
        el.pause = vi.fn();
        Object.defineProperty(el, "duration", { value: 180, configurable: true });
        readerState.audioEl.value = el;
        openWork(controlsLogic, logic, readerState, el);
        controlsLogic.toggleStopAtChapterEnd();

        tick(el, 70);
        tick(el, 121);

        expect(el.pause).toHaveBeenCalled();
        expect(controlsLogic.isStopAtChapterEnd()).toBe(false);
    });

    it("장 중간에서는 아무것도 하지 않는다", () => {
        const readerState = useReaderState();
        const controlsState = useReaderControlsState();
        const controlsLogic = useReaderControlsLogic(controlsState, readerState.audioEl);
        const logic = useReaderLogic(readerState, controlsLogic, {} as AudioListLogic);
        const el = document.createElement("audio");
        el.load = vi.fn();
        el.play = vi.fn().mockResolvedValue(undefined);
        Object.defineProperty(el, "duration", { value: 180, configurable: true });
        readerState.audioEl.value = el;
        openWork(controlsLogic, logic, readerState, el);
        controlsLogic.selectRepeatMode("chapter");

        tick(el, 70);
        tick(el, 90);

        expect(el.currentTime).toBe(90);
    });

    it("반복도 정지도 꺼져 있으면 경계를 그냥 지나간다", () => {
        const readerState = useReaderState();
        const controlsState = useReaderControlsState();
        const controlsLogic = useReaderControlsLogic(controlsState, readerState.audioEl);
        const logic = useReaderLogic(readerState, controlsLogic, {} as AudioListLogic);
        const el = document.createElement("audio");
        el.load = vi.fn();
        el.play = vi.fn().mockResolvedValue(undefined);
        Object.defineProperty(el, "duration", { value: 180, configurable: true });
        readerState.audioEl.value = el;
        openWork(controlsLogic, logic, readerState, el);
        controlsLogic.selectRepeatMode("off");

        tick(el, 70);
        tick(el, 121);

        expect(el.currentTime).toBe(121);
    });
});
