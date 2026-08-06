import { describe, it, expect, beforeEach, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import { useReaderState } from "../Reader/Reader_State.vue";
import { useReaderLogic } from "../Reader/Reader_Logic.vue";
import { useReaderControlsState } from "../Reader/ReaderControls/ReaderControls_State.vue";
import { useReaderControlsLogic } from "../Reader/ReaderControls/ReaderControls_Logic.vue";
import { getBookmarks } from "../services/bookmarks";
import type { AudioListLogic } from "../components/Library/AudioList_Logic.vue";

const SENTENCES = [
    { text: "가장 좋은 것은 물과 같다", start: 0, end: 5000 },
    { text: "물은 만물을 이롭게 하면서도 다투지 않는다", start: 5000, end: 11000 },
];

let workCounter = 0;

function setup() {
    const workId = `work-${++workCounter}`;
    const readerState = useReaderState();
    const controlsState = useReaderControlsState();
    const controlsLogic = useReaderControlsLogic(controlsState, readerState.audioEl);
    const logic = useReaderLogic(readerState, controlsLogic, {} as AudioListLogic);

    const el = document.createElement("audio");
    el.load = vi.fn();
    el.play = vi.fn().mockResolvedValue(undefined);
    readerState.audioEl.value = el;

    logic.openSharedReaderMode("도덕경", SENTENCES, "blob:fake", { audiobookId: workId });
    return { state: readerState, logic, el, workId };
}

beforeEach(() => {
    setActivePinia(createPinia());
    localStorage.clear();
});

// 경전·철학서는 "이 구절을 다시 찾고 싶다"가 잦다. 문장 단위로 저장해 두고
// 나중에 그 지점에서 바로 이어 들을 수 있어야 한다.
describe("문장 북마크", () => {
    it("현재 문장을 저장한다", () => {
        const { state, logic, workId } = setup();
        state.activeIndex.value = 1;

        logic.toggleBookmarkForCurrentSentence();

        const saved = getBookmarks(workId);
        expect(saved).toHaveLength(1);
        expect(saved[0].text).toBe("물은 만물을 이롭게 하면서도 다투지 않는다");
        // 재생 시각을 함께 저장해야 그 지점에서 이어 들을 수 있다.
        expect(saved[0].seconds).toBe(5);
    });

    it("이미 저장한 문장을 다시 누르면 해제한다", () => {
        const { state, logic, workId } = setup();
        state.activeIndex.value = 0;

        logic.toggleBookmarkForCurrentSentence();
        logic.toggleBookmarkForCurrentSentence();

        expect(getBookmarks(workId)).toHaveLength(0);
    });

    it("재생 중인 문장이 없으면 저장하지 않는다", () => {
        const { state, logic, workId } = setup();
        state.activeIndex.value = -1;

        logic.toggleBookmarkForCurrentSentence();

        expect(getBookmarks(workId)).toHaveLength(0);
    });

    it("목록은 문장 순서대로 돌려준다", () => {
        const { state, logic, workId } = setup();
        state.activeIndex.value = 1;
        logic.toggleBookmarkForCurrentSentence();
        state.activeIndex.value = 0;
        logic.toggleBookmarkForCurrentSentence();

        logic.openBookmarkSheet();

        expect(state.bookmarks.value.map((b) => b.sentenceIndex)).toEqual([0, 1]);
    });

    it("저장한 문장을 누르면 그 시각으로 이동한다", () => {
        const { state, logic, el, workId } = setup();
        state.activeIndex.value = 1;
        logic.toggleBookmarkForCurrentSentence();
        logic.openBookmarkSheet();

        logic.goToBookmark(state.bookmarks.value[0]);

        expect(el.currentTime).toBe(5);
        expect(state.isBookmarkSheetOpen.value).toBe(false);
    });

    it("삭제하면 목록에서 바로 사라진다", () => {
        const { state, logic, workId } = setup();
        state.activeIndex.value = 0;
        logic.toggleBookmarkForCurrentSentence();
        logic.openBookmarkSheet();

        logic.removeBookmark(state.bookmarks.value[0]);

        expect(state.bookmarks.value).toHaveLength(0);
        expect(getBookmarks(workId)).toHaveLength(0);
    });

    it("다른 작품의 북마크는 섞이지 않는다", () => {
        const { state, logic, workId } = setup();
        state.activeIndex.value = 0;
        logic.toggleBookmarkForCurrentSentence();

        const otherId = `${workId}-other`;
        logic.openSharedReaderMode("금강경", SENTENCES, "blob:other", { audiobookId: otherId });
        state.activeIndex.value = 1;
        logic.toggleBookmarkForCurrentSentence();

        expect(getBookmarks(workId)).toHaveLength(1);
        expect(getBookmarks(otherId)[0].sentenceIndex).toBe(1);
    });
});
