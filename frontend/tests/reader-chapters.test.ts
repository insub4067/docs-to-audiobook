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
