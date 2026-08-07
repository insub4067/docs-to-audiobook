import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";

import { streamJobAudio } from "../services/progressiveAudio";

/** 서버를 흉내낸다. 폴링할 때마다 states를 하나씩 돌려주고,
 *  청크 요청은 chunkBytes에 있는 것만 200으로 응답한다. */
function mockServer(states: Record<string, unknown>[], chunkBytes: Record<number, string>) {
    let pollCount = 0;
    const chunkRequests: number[] = [];
    const audioRequests: string[] = [];

    const fetchMock = vi.fn(async (url: string) => {
        const chunkMatch = /\/api\/job\/[^/]+\/chunk\/(\d+)$/.exec(url);
        if (chunkMatch) {
            const index = Number(chunkMatch[1]);
            chunkRequests.push(index);
            if (!(index in chunkBytes)) return { ok: false, status: 404 };
            return { ok: true, blob: async () => new Blob([chunkBytes[index]]) };
        }
        if (url.includes("/audio")) {
            audioRequests.push(url);
            return { ok: true, blob: async () => new Blob(["WHOLE"]) };
        }
        const state = states[Math.min(pollCount, states.length - 1)];
        pollCount += 1;
        return { ok: true, json: async () => state };
    });

    vi.stubGlobal("fetch", fetchMock);
    return { chunkRequests, audioRequests, pollCount: () => pollCount };
}

const HEADERS = { Authorization: "Bearer t" };

/** jsdom의 Blob에는 text()/arrayBuffer()가 없어 FileReader로 읽는다.
 *  FileReader는 내부적으로 타이머를 쓰므로 가짜 시계를 먼저 걷어야 한다. */
function readBlob(blob: Blob): Promise<string> {
    vi.useRealTimers();
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result));
        reader.onerror = () => reject(reader.error);
        reader.readAsText(blob);
    });
}

beforeEach(() => {
    vi.useFakeTimers();
});

afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
});

async function runToCompletion(promise: Promise<unknown>) {
    await vi.runAllTimersAsync();
    return await promise;
}

describe("합성 중 점진 수신", () => {
    it("준비된 청크가 생기면 완료를 기다리지 않고 재생 가능하다고 알린다", async () => {
        mockServer(
            [
                { status: "processing", ready_chunks: 1, total_chunks: 3, sentences: [{ text: "첫", start: 0, end: 9 }], completed_chunks: 1 },
                { status: "completed", ready_chunks: 3, total_chunks: 3, sentences: [], headings: [], display_markdown: "", audio_url: "/api/job/j/audio" },
            ],
            { 0: "A", 1: "B", 2: "C" },
        );
        const playable: number[] = [];

        await runToCompletion(
            streamJobAudio("j", HEADERS, { onPlayable: (blob) => playable.push(blob.size) }),
        );

        // 첫 폴링에서 청크 1개(1바이트), 두 번째에서 3개(3바이트)
        expect(playable).toEqual([1, 3]);
    });

    it("청크를 순서대로, 한 번씩만 받는다", async () => {
        const server = mockServer(
            [
                { status: "processing", ready_chunks: 2, total_chunks: 4, sentences: [], completed_chunks: 2 },
                { status: "processing", ready_chunks: 3, total_chunks: 4, sentences: [], completed_chunks: 3 },
                { status: "completed", ready_chunks: 4, total_chunks: 4, sentences: [], headings: [], display_markdown: "", audio_url: "/api/job/j/audio" },
            ],
            { 0: "A", 1: "B", 2: "C", 3: "D" },
        );

        await runToCompletion(streamJobAudio("j", HEADERS, {}));

        expect(server.chunkRequests).toEqual([0, 1, 2, 3]);
    });

    it("모아 둔 청크가 곧 결과물이라 합본을 다시 받지 않는다", async () => {
        // 10만 자 문서면 합본이 수십 MB다. 이미 받은 걸 또 받으면
        // 점진 수신으로 아낀 시간을 전송량으로 돌려주는 셈이 된다.
        const server = mockServer(
            [
                { status: "completed", ready_chunks: 2, total_chunks: 2, sentences: [], headings: [], display_markdown: "", audio_url: "/api/job/j/audio" },
            ],
            { 0: "AB", 1: "CD" },
        );

        const result = await runToCompletion(streamJobAudio("j", HEADERS, {})) as { blob: Blob };

        expect(server.audioRequests).toEqual([]);
        expect(await readBlob(result.blob)).toBe("ABCD");
    });

    it("청크를 못 받았으면 합본으로 받아 온다", async () => {
        // 합성이 끝나는 찰나에 청크 파일이 지워져 404가 날 수 있다.
        const server = mockServer(
            [
                { status: "completed", ready_chunks: 2, total_chunks: 2, sentences: [], headings: [], display_markdown: "", audio_url: "/api/job/j/audio" },
            ],
            {},
        );

        const result = await runToCompletion(streamJobAudio("j", HEADERS, {})) as { blob: Blob };

        expect(server.audioRequests).toEqual(["/api/job/j/audio"]);
        expect(await readBlob(result.blob)).toBe("WHOLE");
    });

    it("서버가 error면 던진다", async () => {
        mockServer([{ status: "error", error: "TTS 연결 실패" }], {});

        const promise = streamJobAudio("j", HEADERS, {});
        const assertion = expect(promise).rejects.toThrow("TTS 연결 실패");
        await vi.runAllTimersAsync();
        await assertion;
    });

    it("진행률을 그대로 전달한다", async () => {
        mockServer(
            [
                { status: "processing", ready_chunks: 0, total_chunks: 5, completed_chunks: 2, sentences: [] },
                { status: "completed", ready_chunks: 0, total_chunks: 5, completed_chunks: 5, sentences: [], headings: [], display_markdown: "", audio_url: "/api/job/j/audio" },
            ],
            {},
        );
        const progress: [number, number][] = [];

        await runToCompletion(
            streamJobAudio("j", HEADERS, { onProgress: (done, total) => progress.push([done, total]) }),
        );

        expect(progress).toEqual([[2, 5], [5, 5]]);
    });

    it("아직 준비된 청크가 없으면 아무것도 요청하지 않는다", async () => {
        const server = mockServer(
            [
                { status: "processing", ready_chunks: 0, total_chunks: 5, completed_chunks: 0, sentences: [] },
                { status: "completed", ready_chunks: 5, total_chunks: 5, sentences: [], headings: [], display_markdown: "", audio_url: "/api/job/j/audio" },
            ],
            { 0: "A", 1: "B", 2: "C", 3: "D", 4: "E" },
        );

        await runToCompletion(streamJobAudio("j", HEADERS, {}));

        expect(server.chunkRequests).toEqual([0, 1, 2, 3, 4]);
    });
});
