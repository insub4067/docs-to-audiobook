// 서점 시리즈(부로 나뉜 작품)의 재생목록.
//
// 확인하려는 것은 "부를 하나 틀면 거기서부터 끝까지 이어 들린다"는 것과,
// 그 이어짐이 화면이 꺼진 상태에서도 끊기지 않는다는 것이다. 후자는
// onEnded가 동기로 남아 있고 다음 부를 미리 받아 두는 것에 달려 있다.
import { createPinia, setActivePinia } from "pinia";
import { describe, it, expect, beforeEach, vi } from "vitest";

import { useLibraryState, type LibraryPart, type LibraryItem } from "../Library/Library_State.vue";
import { useLibraryLogic } from "../Library/Library_Logic.vue";
import type { ReaderLogic } from "../Reader/Reader_Logic.vue";

const WORK = {
    id: "work-1",
    title: "오디세이",
    library_category: "고전문학",
    library_edition: null,
    library_translator: null,
    library_source: null,
    library_rights: null,
    library_description: null,
    library_chapter_count: null,
    duration_seconds: 120,
    created_at: "",
    audio_url: "https://example.com/part-1.mp3",
    sentences_url: null,
    part_count: 3,
} as LibraryItem;

const PARTS: LibraryPart[] = [
    { id: "part-1", part_number: 1, part_title: "제1권", duration_seconds: 120, audio_url: "https://example.com/1.mp3", sentences_url: null },
    { id: "part-2", part_number: 2, part_title: "제2권", duration_seconds: 130, audio_url: "https://example.com/2.mp3", sentences_url: null },
    { id: "part-3", part_number: 3, part_title: "제3권", duration_seconds: 140, audio_url: "https://example.com/3.mp3", sentences_url: null },
];

/** openSharedReaderMode에 넘어온 인자를 모아 두는 가짜 리더. */
function makeReaderLogic() {
    const opened: { title: string; audioUrl: string; options: Record<string, unknown> }[] = [];
    const logic = {
        openSharedReaderMode: vi.fn((title: string, _sentences: unknown, audioUrl: string, options = {}) => {
            opened.push({ title, audioUrl, options: options as Record<string, unknown> });
        }),
    } as unknown as ReaderLogic;
    return { logic, opened };
}

/** 마지막으로 열린 오디오의 onEnded를 부른다 — 재생이 끝난 상황. */
function endCurrentPart(opened: ReturnType<typeof makeReaderLogic>["opened"], repeatMode = "off") {
    const last = opened[opened.length - 1];
    (last.options.onEnded as (mode: string) => void)(repeatMode);
}

/** 미리 받아 둔 것이 없으면 문장 데이터를 받아 온 뒤에 다음 부가 열린다.
 *  마이크로태스크 하나를 비워 그 경로를 기다린다. */
function flush() {
    return new Promise((resolve) => setTimeout(resolve, 0));
}

describe("서점 시리즈 재생목록", () => {
    beforeEach(() => {
        // Library_Logic이 useAuthLogic을 거쳐 pinia 스토어를 읽는다.
        setActivePinia(createPinia());
        const state = useLibraryState();
        state.queueParts.value = [];
        state.queueIndex.value = -1;
        state.queueWork.value = null;
        state.queueFetchedAt.value = 0;
        state.prefetchedNextPart.value = null;
        state.detailParts.value = [];
        state.detailItem.value = null;
        state.playbackSeconds.value = {};
        state.isDetailOpen.value = true;
        vi.restoreAllMocks();
    });

    it("부를 틀면 재생목록 종류가 library로 잡힌다", async () => {
        const state = useLibraryState();
        const { logic: readerLogic, opened } = makeReaderLogic();
        const logic = useLibraryLogic(state, readerLogic);

        await logic.playPart(WORK, PARTS, 0);

        expect(opened).toHaveLength(1);
        expect(opened[0].options.playlistKind).toBe("library");
        // 부마다 audiobooks 행이 따로 있어, 재생 위치도 부 단위로 저장된다.
        expect(opened[0].options.audiobookId).toBe("part-1");
        expect(state.queueIndex.value).toBe(0);
        expect(state.queueWork.value?.id).toBe("work-1");
    });

    it("한 부가 끝나면 다음 부로 이어진다", async () => {
        const state = useLibraryState();
        const { logic: readerLogic, opened } = makeReaderLogic();
        const logic = useLibraryLogic(state, readerLogic);

        await logic.playPart(WORK, PARTS, 0);
        endCurrentPart(opened);
        await flush();

        expect(state.queueIndex.value).toBe(1);
        expect(opened[1].audioUrl).toBe("https://example.com/2.mp3");
        // 이어지는 부는 읽기 화면을 다시 펼치지 않는다 — 듣는 중에 화면이
        // 제멋대로 열리면 안 된다.
        expect(opened[1].options.openReaderUI).toBe(false);
    });

    it("가운데 부에서 시작해도 다음 부로 이어진다", async () => {
        // 뉴스와 다른 점이다. 뉴스는 "전체 듣기"로 시작했을 때만 이어지지만,
        // 책의 다음 장은 어디서 시작했든 이어지는 게 당연하다.
        const state = useLibraryState();
        const { logic: readerLogic, opened } = makeReaderLogic();
        const logic = useLibraryLogic(state, readerLogic);

        await logic.playPart(WORK, PARTS, 1);
        endCurrentPart(opened);
        await flush();

        expect(state.queueIndex.value).toBe(2);
        expect(opened[1].audioUrl).toBe("https://example.com/3.mp3");
    });

    it("마지막 부가 끝나면 멈춘다", async () => {
        const state = useLibraryState();
        const { logic: readerLogic, opened } = makeReaderLogic();
        const logic = useLibraryLogic(state, readerLogic);

        await logic.playPart(WORK, PARTS, 2);
        endCurrentPart(opened);

        expect(opened).toHaveLength(1);
        expect(state.queueIndex.value).toBe(-1);
    });

    it("전체 반복이면 마지막 부에서 1부로 돌아온다", async () => {
        const state = useLibraryState();
        const { logic: readerLogic, opened } = makeReaderLogic();
        const logic = useLibraryLogic(state, readerLogic);

        await logic.playPart(WORK, PARTS, 2);
        endCurrentPart(opened, "all");
        await flush();

        expect(state.queueIndex.value).toBe(0);
        expect(opened[1].audioUrl).toBe("https://example.com/1.mp3");
    });

    it("다음 부로 넘어갈 때 네트워크를 기다리지 않는다", async () => {
        // ⚠️ 이게 이 파일에서 가장 중요한 확인이다. onEnded 안에서 await를
        // 하나라도 타면, 화면이 꺼져 있는 동안 실행이 밀려 새 소스에 대한
        // play()가 자동재생으로 막힌다 — 다음 부가 안 이어진다.
        const state = useLibraryState();
        const { logic: readerLogic, opened } = makeReaderLogic();
        const logic = useLibraryLogic(state, readerLogic);

        await logic.playPart(WORK, PARTS, 0);
        // 미리 받아 둔 것이 있는 상태를 만든다(문장 데이터가 없는 부라
        // prepareNextPart가 네트워크 없이 채운다).
        state.prefetchedNextPart.value = { id: "part-2", part: PARTS[1], sentences: [] };

        endCurrentPart(opened);

        // await 없이, onEnded가 반환되기 전에 이미 다음 부가 열려 있어야 한다.
        expect(opened).toHaveLength(2);
        expect(opened[1].audioUrl).toBe("https://example.com/2.mp3");
        // 한 번 쓴 미리받기는 버린다.
        expect(state.prefetchedNextPart.value).toBeNull();
    });

    it("이어 듣기는 마지막으로 듣던 부에서 재개한다", async () => {
        // 작품 id는 곧 1부의 id다. 그대로 이어 들으면 3부까지 듣고 앱을
        // 껐다 켠 사람이 1부로 돌아간다.
        const state = useLibraryState();
        state.detailItem.value = WORK;
        state.detailParts.value = PARTS;
        state.playbackSeconds.value = { "part-1": 120, "part-2": 45 };
        state.fetchedAt.value = Date.now();
        state.items.value = [WORK];

        const { logic: readerLogic, opened } = makeReaderLogic();
        const logic = useLibraryLogic(state, readerLogic);

        await logic.playFromLastPosition(WORK);

        expect(state.queueIndex.value).toBe(1);
        expect(opened[0].options.audiobookId).toBe("part-2");
        expect(opened[0].options.resumeSeconds).toBe(45);
    });

    it("재생 이력이 없으면 이어 듣기도 1부부터 튼다", async () => {
        const state = useLibraryState();
        state.detailItem.value = WORK;
        state.detailParts.value = PARTS;
        state.fetchedAt.value = Date.now();
        state.items.value = [WORK];

        const { logic: readerLogic, opened } = makeReaderLogic();
        const logic = useLibraryLogic(state, readerLogic);

        await logic.playFromLastPosition(WORK);

        expect(state.queueIndex.value).toBe(0);
        expect(opened[0].options.audiobookId).toBe("part-1");
    });

    it("읽기 화면 제목에 작품명과 부 제목이 함께 나온다", async () => {
        // 미니 플레이어와 잠금화면에는 이 제목만 보인다. 부 제목만 있으면
        // 무슨 책을 듣고 있었는지 알 수 없다.
        const state = useLibraryState();
        const { logic: readerLogic, opened } = makeReaderLogic();
        const logic = useLibraryLogic(state, readerLogic);

        await logic.playPart(WORK, PARTS, 1);

        expect(opened[0].title).toBe("오디세이 · 제2권");
    });
});
