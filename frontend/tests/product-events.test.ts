import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import { useReaderState } from "../Reader/Reader_State.vue";
import { useReaderLogic } from "../Reader/Reader_Logic.vue";
import { useReaderControlsState } from "../Reader/ReaderControls/ReaderControls_State.vue";
import { useReaderControlsLogic } from "../Reader/ReaderControls/ReaderControls_Logic.vue";
import type { AudioListLogic } from "../components/Library/AudioList_Logic.vue";
import { useNotificationsState } from "../Notifications/Notifications_State.vue";
import { useNotificationsLogic } from "../Notifications/Notifications_Logic.vue";
import { useAuthStore } from "../stores/auth";

const SENTENCES = [{ text: "첫 문장", start: 0, end: 1000 }];

/** /api/events로 나간 event_name만 뽑는다. */
function trackedEvents(fetchMock: ReturnType<typeof vi.fn>): string[] {
    return fetchMock.mock.calls
        .filter(([url]) => String(url) === "/api/events")
        .map(([, init]) => JSON.parse((init as RequestInit).body as string).event_name);
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
    setActivePinia(createPinia());
    localStorage.clear();
    localStorage.setItem("authToken", "token-1");
    fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
    vi.unstubAllGlobals();
});

// 회귀: 관리자 대시보드의 "첫 재생" 지표가 0건으로 고정돼 있었다.
// playback_started를 찍는 코드가 앱 어디에도 없어서, 지표는 구현됐지만
// 데이터가 전혀 들어오지 않았다.
describe("재생 시작 이벤트", () => {
    function setupReader() {
        const readerState = useReaderState();
        const controlsState = useReaderControlsState();
        const controlsLogic = useReaderControlsLogic(controlsState, readerState.audioEl);
        const readerLogic = useReaderLogic(readerState, controlsLogic, {} as AudioListLogic);

        const el = document.createElement("audio");
        el.load = vi.fn();
        el.play = vi.fn().mockResolvedValue(undefined);
        readerState.audioEl.value = el;

        return { readerLogic, el };
    }

    it("재생이 시작되면 playback_started를 기록한다", () => {
        const { readerLogic, el } = setupReader();

        readerLogic.openSharedReaderMode("뉴스1", SENTENCES, "blob:fake", {});
        el.onplay?.(new Event("play"));

        expect(trackedEvents(fetchMock)).toEqual(["playback_started"]);
    });

    it("일시정지 후 다시 재생해도 한 번만 기록한다", () => {
        // "첫 재생"은 콘텐츠를 연 횟수지 play 버튼을 누른 횟수가 아니다.
        const { readerLogic, el } = setupReader();

        readerLogic.openSharedReaderMode("뉴스1", SENTENCES, "blob:fake", {});
        el.onplay?.(new Event("play"));
        el.onpause?.(new Event("pause"));
        el.onplay?.(new Event("play"));

        expect(trackedEvents(fetchMock)).toEqual(["playback_started"]);
    });

    it("다른 콘텐츠를 열면 다시 기록한다", () => {
        const { readerLogic, el } = setupReader();

        readerLogic.openSharedReaderMode("뉴스1", SENTENCES, "blob:fake", {});
        el.onplay?.(new Event("play"));
        readerLogic.openSharedReaderMode("뉴스2", SENTENCES, "blob:fake2", {});
        el.onplay?.(new Event("play"));

        expect(trackedEvents(fetchMock)).toEqual(["playback_started", "playback_started"]);
    });
});

// 회귀: 생성 성공률이 3.7%(54건 시작 / 2건 완료)로 잡혔다. 대용량 문서는
// 백그라운드 작업으로 넘어가면서 Generation_Logic이 즉시 반환해버려,
// generation_started만 남고 완료/실패 이벤트가 영영 찍히지 않았다.
describe("백그라운드 생성 완료 이벤트", () => {
    function respondWithJob(job: Record<string, unknown>) {
        fetchMock.mockImplementation(async (url: string) => {
            if (String(url).startsWith("/api/background-jobs/")) {
                return { ok: true, json: async () => job };
            }
            return { ok: true, json: async () => ({}) };
        });
    }

    /** 로그인 상태로 알림 로직을 켜고, 대기 중인 작업 하나를 등록해 폴링시킨다. */
    async function pollOneJob(job: Record<string, unknown>): Promise<void> {
        useAuthStore().setSession(
            { id: "user-1", email: "a@b.c", is_admin: false }, "token-1",
        );
        respondWithJob(job);
        const logic = useNotificationsLogic(useNotificationsState());
        await logic.initialize();
        (window as any).__rememberBackgroundJob("job-1");
        await (window as any).__checkPendingBackgroundJobs();
    }

    beforeEach(() => {
        (window as any).__syncAudiobooksToCloud = vi.fn().mockResolvedValue({ ok: true });
    });

    afterEach(() => {
        delete (window as any).__syncAudiobooksToCloud;
        localStorage.clear();
    });

    it("백그라운드 작업이 완료되면 generation_completed를 기록한다", async () => {
        await pollOneJob({ status: "completed" });

        expect(trackedEvents(fetchMock)).toEqual(["generation_completed"]);
    });

    it("백그라운드 작업이 실패하면 generation_failed를 기록한다", async () => {
        await pollOneJob({ status: "error", error: "변환 실패" });

        expect(trackedEvents(fetchMock)).toEqual(["generation_failed"]);
    });

    it("아직 진행 중이면 아무 이벤트도 기록하지 않는다", async () => {
        await pollOneJob({ status: "processing" });

        expect(trackedEvents(fetchMock)).toEqual([]);
    });
});
