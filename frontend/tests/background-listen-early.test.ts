import { createPinia, setActivePinia } from "pinia";
import { describe, it, expect, beforeEach, vi } from "vitest";

import { useAudioListState } from "../components/Library/AudioList_State.vue";
import { useAudioListLogic } from "../components/Library/AudioList_Logic.vue";

// 서버는 백그라운드(대용량) 작업에도 준비된 앞 구간을 내준다. 그런데 그걸
// 받아 오는 코드가 모달을 켜둔 포그라운드 경로에만 붙어 있어서, 앱을 나갔다
// 오면 합성이 끝날 때까지 아무것도 들을 수 없었다 — 정작 기다림이 가장 긴
// 문서(스캔본 등)가 전부 이쪽으로 온다.

const openPartialReader = vi.fn();

/** streamJobAudio를 대신한다. onPlayable을 부르고 끝난다. */
vi.mock("../services/progressiveAudio", () => ({
    streamJobAudio: vi.fn(async (_jobId: string, _headers: unknown, handlers: {
        onPlayable?(blob: Blob, sentences: unknown[]): void;
    }) => {
        handlers.onPlayable?.(new Blob(["앞구간"], { type: "audio/mpeg" }), [{ text: "첫 문장", start: 0, end: 1 }]);
        return { blob: new Blob(), sentences: [], headings: [], displayMarkdown: "" };
    }),
}));

vi.mock("../services/indexedDb", () => ({
    getAllAudiobooksFromDB: async () => [],
    saveAudiobookToDB: async () => {},
    deleteAudiobookFromDB: async () => {},
    getAudiobookFromDB: async () => null,
    DEFAULT_BOOK_ID: "default",
    DEFAULT_BOOK_DISMISSED_KEY: "dismissed",
}));

beforeEach(async () => {
    setActivePinia(createPinia());
    // 모의 호출 수는 파일 안에서 누적된다 — 테스트마다 초기화한다.
    const { streamJobAudio } = await import("../services/progressiveAudio");
    vi.mocked(streamJobAudio).mockClear();
    openPartialReader.mockClear();
    (window as any).__openPartialReaderMode = openPartialReader;
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({}) })));
});

function setup() {
    const state = useAudioListState();
    const logic = useAudioListLogic(state);
    logic.showBackgroundJob("job-1", "스캔본.mp3", null);
    return { state, logic };
}

describe("백그라운드 작업 먼저 듣기", () => {
    it("누르면 받아 둔 앞 구간으로 읽기 화면을 연다", async () => {
        const { logic } = setup();

        await logic.listenEarlyToBackgroundJob("job-1");

        expect(openPartialReader).toHaveBeenCalledTimes(1);
        const [title, sentences] = openPartialReader.mock.calls[0];
        expect(title).toBe("스캔본.mp3");
        expect(sentences).toHaveLength(1);
    });

    it("받은 앞 구간을 항목에 남겨 다시 열 수 있게 한다", async () => {
        const { state, logic } = setup();

        await logic.listenEarlyToBackgroundJob("job-1");

        const item = state.backgroundJobItems.value.find((entry) => entry.jobId === "job-1");
        expect(item?.playableAudio).toBeInstanceOf(Blob);
        expect(item?.isPreparingPreview).toBe(false);
    });

    it("이미 받아 둔 뒤 다시 누르면 다시 받지 않고 바로 연다", async () => {
        const { logic } = setup();
        const { streamJobAudio } = await import("../services/progressiveAudio");

        await logic.listenEarlyToBackgroundJob("job-1");
        await logic.listenEarlyToBackgroundJob("job-1");

        expect(streamJobAudio).toHaveBeenCalledTimes(1);
        expect(openPartialReader).toHaveBeenCalledTimes(2);
    });

    it("목록에 없는 작업은 아무 일도 하지 않는다", async () => {
        const { logic } = setup();

        await logic.listenEarlyToBackgroundJob("없는-작업");

        expect(openPartialReader).not.toHaveBeenCalled();
    });
});
