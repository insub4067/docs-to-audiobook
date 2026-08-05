import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import { useAudioListState } from "../components/Library/AudioList_State.vue";
import { useAudioListLogic } from "../components/Library/AudioList_Logic.vue";
import { getAudiobookFromDB, initDB, DEFAULT_BOOK_ID, DEFAULT_BOOK_DISMISSED_KEY } from "../services/indexedDb";

const DEFAULT_BOOK_META = {
    status: "ready",
    title: "데미안",
    sentences: [{ text: "문장", start: 0, end: 1000 }],
    headings: [],
    char_count: 4,
    audio_url: "/api/default-book/audio",
    version: "v1",
};

function stubFetch() {
    return vi.fn(async (url: string) => {
        if (url === "/api/default-book") {
            return new Response(JSON.stringify(DEFAULT_BOOK_META), { status: 200 });
        }
        if (url === "/api/default-book/audio") {
            return new Response(new Uint8Array([1, 2, 3]).buffer, { status: 200 });
        }
        throw new Error(`stubFetch: 예상 못한 요청 ${url}`);
    });
}

beforeEach(async () => {
    setActivePinia(createPinia());
    localStorage.clear();
    vi.stubGlobal("fetch", stubFetch());
    // deleteDatabase는 이전 테스트에서 연 커넥션이 남아 있으면 그게 닫힐
    // 때까지 무한정 기다린다(fake-indexeddb도 스펙대로 동작). DB 자체를
    // 다시 만드는 대신 매 테스트마다 스토어 내용만 비운다.
    const db = await initDB();
    await new Promise<void>((resolve, reject) => {
        const tx = db.transaction(["audiobooks"], "readwrite");
        tx.objectStore("audiobooks").clear();
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
    });
});

afterEach(() => {
    vi.unstubAllGlobals();
});

// 회귀: "로그인 사용자는 서재에서 기본 제공 오디오북을 지울 수 있어야
// 한다"는 요청. 단순히 IndexedDB에서 지우는 것만으로는 부족하다 — 화면을
// 새로고침(=load()가 다시 돎)하면 seedDefaultBookIfNeeded()가 "없으니
// 다시 채워야지" 하고 되살렸었다. 삭제 여부를 별도로 기억해야 한다.
describe("기본 제공 오디오북 삭제", () => {
    it("삭제 후 다시 load()해도 되살아나지 않는다", async () => {
        const state = useAudioListState();
        const logic = useAudioListLogic(state);

        await logic.load();
        expect(await getAudiobookFromDB(DEFAULT_BOOK_ID)).toBeDefined();

        await logic.deleteAudiobook(DEFAULT_BOOK_ID);
        expect(await getAudiobookFromDB(DEFAULT_BOOK_ID)).toBeUndefined();

        // 다음 방문(=load 재호출)에서 다시 채워 넣으면 안 된다.
        await logic.load();
        expect(await getAudiobookFromDB(DEFAULT_BOOK_ID)).toBeUndefined();
    });

    it("로그아웃하면(표시 해제) 다음 방문자를 위해 다시 채워진다", async () => {
        const state = useAudioListState();
        const logic = useAudioListLogic(state);

        await logic.load();
        await logic.deleteAudiobook(DEFAULT_BOOK_ID);
        expect(localStorage.getItem(DEFAULT_BOOK_DISMISSED_KEY)).toBe("1");

        // Auth_Logic.logout()이 하는 것과 동일 — 로그아웃 확인 다이얼로그가
        // "기본 제공 오디오북만 남습니다"라고 약속하므로 지워둔 표시도 함께 지운다.
        localStorage.removeItem(DEFAULT_BOOK_DISMISSED_KEY);

        await logic.load();
        expect(await getAudiobookFromDB(DEFAULT_BOOK_ID)).toBeDefined();
    });

    it("일반 오디오북을 지워도 기본 제공 오디오북 표시는 건드리지 않는다", async () => {
        const state = useAudioListState();
        const logic = useAudioListLogic(state);
        await logic.load();

        await logic.deleteAudiobook("some-other-audiobook-id");
        expect(localStorage.getItem(DEFAULT_BOOK_DISMISSED_KEY)).toBeNull();
    });
});
