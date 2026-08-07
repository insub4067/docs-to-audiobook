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

// 미니 플레이어에서 항목을 넘길 때는 읽기 화면이 펼쳐지면 안 된다.
// 호출부가 옵션을 넘기는 것만 확인하면 옵션을 무시하는 회귀를 놓친다 —
// 여기서는 실제 openSharedReaderMode의 동작을 본다.
describe("읽기 화면 펼침 여부", () => {
    it("openReaderUI가 false면 읽기 화면을 펼치지 않는다", () => {
        const { state, logic } = setup();
        state.isOpen.value = false;

        logic.openSharedReaderMode("기사", [{ text: "문장", start: 0, end: 1000 }], "blob:x", {
            openReaderUI: false,
        });

        expect(state.isOpen.value).toBe(false);
    });

    it("기본값은 펼치는 것이다", () => {
        // 뉴스 카드나 라이브러리에서 처음 재생할 때는 읽기 화면이 떠야 한다.
        const { state, logic } = setup();
        state.isOpen.value = false;

        logic.openSharedReaderMode("작품", [{ text: "문장", start: 0, end: 1000 }], "blob:y", {});

        expect(state.isOpen.value).toBe(true);
    });
});

// 장 이동은 경전·고전 청취의 주된 이동 수단인데 "더보기" 시트 안에 2탭
// 깊이로 있었다. 하단 컨트롤로 올리면서, 목차가 없는 개인 문서에서는
// 나타나지 않아야 한다는 조건이 함께 생겼다.
describe("하단 재생 컨트롤의 장 이동 버튼", () => {
    async function mountReader(headings: typeof CHAPTERS | []) {
        const { mount } = await import("@vue/test-utils");
        const ReaderView = (await import("../Reader/Reader_View.vue")).default;
        const { state, logic } = setup();
        state.headings.value = [...headings];
        state.isOpen.value = true;

        const controlsState = useReaderControlsState();
        const wrapper = mount(ReaderView, {
            props: {
                state, logic,
                controlsState,
                controlsLogic: useReaderControlsLogic(controlsState, state.audioEl),
                audioListLogic: {} as AudioListLogic,
                audioListState: { savedAudiobooks: { value: [] } } as never,
                themeLogic: {} as never,
            },
            global: { stubs: { IndexSheetView: true, BookmarkSheetView: true, ReaderMoreSheetView: true,
                ReaderSettingsSheetView: true, ReaderOptionsSheetView: true, ReaderPlaylistSheetView: true,
                ReaderControlsView: true } },
        });
        // ReaderView가 자기 <audio>를 ref로 물려서 setup()이 넣어 둔 스텁을
        // 덮어쓴다. jsdom은 play()를 구현하지 않으므로 여기서 다시 막는다.
        state.audioEl.value!.play = vi.fn().mockResolvedValue(undefined);
        return wrapper;
    }

    it("장이 여러 개면 이전/다음 장 버튼이 하단에 보인다", async () => {
        const wrapper = await mountReader(CHAPTERS);

        expect(wrapper.findAll(".btn-player-chapter")).toHaveLength(2);
        wrapper.unmount();
    });

    it("목차가 없는 문서에서는 나타나지 않는다", async () => {
        // 개인 PDF 대부분이 여기 해당한다. 눌러도 갈 곳이 없는 버튼을
        // 상시 노출하면 하단이 그만큼 좁아진다.
        const wrapper = await mountReader([]);

        expect(wrapper.findAll(".btn-player-chapter")).toHaveLength(0);
        wrapper.unmount();
    });

    it("10초 이동 버튼을 밀어내지 않는다", async () => {
        // 보고서는 ⏮⏭를 장 이동으로 "교체"하라고 했지만, 목차 없는 문서에서는
        // 10초 이동이 유일한 이동 수단이다. 추가하되 대체하지 않는다.
        const wrapper = await mountReader(CHAPTERS);

        expect(wrapper.findAll(".btn-player-skip")).toHaveLength(2);
        wrapper.unmount();
    });

    it("다음 장 버튼을 누르면 다음 장으로 간다", async () => {
        const wrapper = await mountReader(CHAPTERS);
        const state = wrapper.props("state") as ReturnType<typeof useReaderState>;
        state.activeIndex.value = 0;
        state.audioEl.value!.currentTime = 5;

        await wrapper.findAll(".btn-player-chapter")[1].trigger("click");

        expect(state.audioEl.value!.currentTime).toBe(60);
        wrapper.unmount();
    });
});
