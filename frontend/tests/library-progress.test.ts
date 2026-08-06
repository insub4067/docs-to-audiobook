import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import { useLibraryState, type LibraryItem } from "../Library/Library_State.vue";
import { useLibraryLogic } from "../Library/Library_Logic.vue";
import type { ReaderLogic } from "../Reader/Reader_Logic.vue";

/** 12시간짜리 경전 하나. 라이브러리 작품은 이렇게 길어서 진행률이 중요하다. */
function work(overrides: Partial<LibraryItem> = {}): LibraryItem {
    return {
        id: "book-1",
        title: "도덕경",
        library_category: "철학·사상",
        library_edition: null,
        library_translator: null,
        library_source: null,
        library_rights: null,
        library_description: null,
        library_chapter_count: 81,
        duration_seconds: 3600,
        created_at: "2026-08-01",
        audio_url: "blob:fake",
        sentences_url: null,
        ...overrides,
    };
}

let fetchMock: ReturnType<typeof vi.fn>;

function setup() {
    const state = useLibraryState();
    state.playbackSeconds.value = {};
    return { state, logic: useLibraryLogic(state, {} as ReaderLogic) };
}

beforeEach(() => {
    setActivePinia(createPinia());
    localStorage.clear();
    localStorage.setItem("authToken", "token-1");
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
    vi.unstubAllGlobals();
});

describe("라이브러리 목록의 청취 진행률", () => {
    it("재생 위치를 한 번의 요청으로 받아온다", async () => {
        // 카드마다 따로 부르면 작품 수만큼 요청이 나간다(N+1).
        const { state, logic } = setup();
        fetchMock.mockResolvedValue({ ok: true, json: async () => ({ positions: { "book-1": 1800 } }) });

        await logic.loadPlaybackPositions();

        expect(fetchMock).toHaveBeenCalledTimes(1);
        expect(String(fetchMock.mock.calls[0][0])).toBe("/api/library/playback");
        expect(state.playbackSeconds.value).toEqual({ "book-1": 1800 });
    });

    it("들은 적 없는 작품은 진행률을 보여주지 않는다", () => {
        const { logic } = setup();

        expect(logic.getProgress(work())).toBeNull();
    });

    it("듣는 중이면 퍼센트와 남은 시간을 계산한다", () => {
        const { state, logic } = setup();
        state.playbackSeconds.value = { "book-1": 900 };

        const progress = logic.getProgress(work())!;

        expect(progress.percent).toBe(25);
        expect(progress.isFinished).toBe(false);
        expect(progress.remainingLabel).toBe("약 45분 남음");
    });

    it("끝까지 다 듣지 않아도 97%를 넘으면 완료로 본다", () => {
        // 문장 끝에서 멈추거나 저장이 30초 간격이라 마지막 몇 초는 흔히 안 채워진다.
        const { state, logic } = setup();
        state.playbackSeconds.value = { "book-1": 3500 };

        expect(logic.getProgress(work())!.isFinished).toBe(true);
    });

    it("재생시간을 모르는 작품은 진행률을 만들지 않는다", () => {
        // 0으로 나누면 Infinity가 되어 막대가 깨진다.
        const { state, logic } = setup();
        state.playbackSeconds.value = { "book-1": 900 };

        expect(logic.getProgress(work({ duration_seconds: null }))).toBeNull();
    });

    it("로그아웃 상태에서는 요청하지 않고 진행률을 비운다", async () => {
        const { state, logic } = setup();
        state.playbackSeconds.value = { "book-1": 900 };
        localStorage.removeItem("authToken");

        await logic.loadPlaybackPositions();

        expect(fetchMock).not.toHaveBeenCalled();
        expect(state.playbackSeconds.value).toEqual({});
    });
});
