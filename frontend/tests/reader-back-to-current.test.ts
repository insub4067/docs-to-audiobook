import { describe, it, expect, beforeEach, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import { useReaderState } from "../Reader/Reader_State.vue";
import { useReaderLogic } from "../Reader/Reader_Logic.vue";
import { useReaderControlsState } from "../Reader/ReaderControls/ReaderControls_State.vue";
import { useReaderControlsLogic } from "../Reader/ReaderControls/ReaderControls_Logic.vue";
import type { AudioListLogic } from "../components/Library/AudioList_Logic.vue";

// 회귀: "현재 위치로" 화살표가 항상 위를 가리켰다. 읽던 곳보다 재생 위치가
// 아래에 있어도 위쪽 화살표라, 누르면 반대로 갈 것처럼 보였다.
//
// ⚠️ jsdom에는 레이아웃이 없어 getBoundingClientRect가 전부 0을 돌려준다.
// 그대로 두면 모든 문장이 "위로 벗어남"으로 판정돼 테스트가 통과해도 아무것도
// 증명하지 못한다. 그래서 사각형을 직접 심는다.
function rect(top: number, bottom: number): DOMRect {
    return { top, bottom, left: 0, right: 0, width: 0, height: bottom - top, x: 0, y: top, toJSON: () => ({}) } as DOMRect;
}

function stubRect(el: HTMLElement, top: number, bottom: number): void {
    el.getBoundingClientRect = () => rect(top, bottom);
}

/** 뷰포트는 화면 좌표 100~700. 활성 문장을 sentenceTop~sentenceBottom에 놓는다. */
function setup(sentenceTop: number, sentenceBottom: number) {
    const state = useReaderState();
    const controlsState = useReaderControlsState();
    const controlsLogic = useReaderControlsLogic(controlsState, state.audioEl);
    const logic = useReaderLogic(state, controlsLogic, {} as AudioListLogic);

    const content = document.createElement("div");
    stubRect(content, 100, 700);
    state.contentEl.value = content;

    const span = document.createElement("span");
    span.id = "sent-3";
    stubRect(span, sentenceTop, sentenceBottom);
    document.body.appendChild(span);

    state.activeIndex.value = 3;
    return { state, logic, span };
}

beforeEach(() => {
    setActivePinia(createPinia());
    document.body.innerHTML = "";
    vi.useRealTimers();
});

describe("현재 위치로 — 버튼 표시", () => {
    it("활성 문장이 보이면 버튼을 띄우지 않는다", () => {
        const { state, logic } = setup(300, 340);

        logic.onReaderContentScroll();

        expect(state.isScrolledAway.value).toBe(false);
    });

    it("활성 문장이 화면 밖이면 버튼을 띄운다", () => {
        const { state, logic } = setup(20, 60);

        logic.onReaderContentScroll();

        expect(state.isScrolledAway.value).toBe(true);
    });

    it("경계에 걸쳐 일부만 보여도 벗어난 것으로 보지 않는다", () => {
        // 문장 아래쪽만 뷰포트 위 경계에 걸친 상태. 읽는 사람에게는 보인다.
        const { state, logic } = setup(60, 140);

        logic.onReaderContentScroll();

        expect(state.isScrolledAway.value).toBe(false);
    });
});

describe("현재 위치로 — 화살표 방향", () => {
    it("⚠️ 재생 위치가 아래에 있으면 아래를 가리킨다", () => {
        // 이게 이번 버그다. 사용자가 위로 스크롤해 앞부분을 읽는 상황 —
        // 재생 중인 문장은 화면보다 아래에 있으므로 내려가야 한다.
        const { state, logic } = setup(900, 940);

        logic.onReaderContentScroll();

        expect(state.isScrolledAway.value).toBe(true);
        expect(state.isCurrentBelow.value).toBe(true);
    });

    it("재생 위치가 위에 있으면 위를 가리킨다", () => {
        // 아래로 스크롤해 앞서 읽는 상황.
        const { state, logic } = setup(20, 60);

        logic.onReaderContentScroll();

        expect(state.isScrolledAway.value).toBe(true);
        expect(state.isCurrentBelow.value).toBe(false);
    });

    it("위아래를 오가면 방향도 따라 바뀐다", () => {
        const { state, logic, span } = setup(900, 940);
        logic.onReaderContentScroll();
        expect(state.isCurrentBelow.value).toBe(true);

        stubRect(span, 20, 60);
        logic.onReaderContentScroll();

        expect(state.isCurrentBelow.value).toBe(false);
    });
});
