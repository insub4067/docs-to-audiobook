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

/** 문장 배열 전체를 2초마다 다시 보내던 것을 델타로 바꿨다. 클라이언트가
 *  받아 둔 개수를 ?since=로 알리면 서버는 그 뒤만 잘라 준다.
 *
 *  이 목 서버는 진짜 서버처럼 since를 실제로 반영한다 — 위쪽 mockServer는
 *  since를 무시하므로 이어붙이기가 틀려도 통과한다. */
function deltaServer(allSentences: { text: string }[], readyAfter: number) {
    const sinceValues: number[] = [];
    let polls = 0;

    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
        if (/\/chunk\/\d+$/.test(url)) return { ok: true, blob: async () => new Blob(["X"]) };
        if (url.includes("/audio")) return { ok: true, blob: async () => new Blob(["WHOLE"]) };

        const since = Number(new URL(url, "http://x").searchParams.get("since"));
        sinceValues.push(since);
        polls += 1;

        // readyAfter번째 폴링까지는 문장이 하나씩 늘어나고, 그다음 완료된다.
        if (polls <= readyAfter) {
            return { ok: true, json: async () => ({
                status: "processing", ready_chunks: 0, total_chunks: 1, completed_chunks: polls,
                sentences: allSentences.slice(since, polls),
            }) };
        }
        // 완료 응답은 최종본 전체다(서버가 타이밍을 다시 매겨 갈아끼운다).
        return { ok: true, json: async () => ({
            status: "completed", ready_chunks: 1, total_chunks: 1,
            sentences: allSentences, headings: [], display_markdown: "", audio_url: "/api/job/j/audio",
        }) };
    }));

    return { sinceValues: () => sinceValues };
}

describe("문장 델타 수신", () => {
    const ALL = [{ text: "첫" }, { text: "둘" }, { text: "셋" }];

    it("이미 받아 둔 문장 수를 since로 보낸다", async () => {
        const server = deltaServer(ALL, 3);

        await runToCompletion(streamJobAudio("j", HEADERS, {}));

        // 0개 → 1개 → 2개 → 3개 순으로 누적된 개수를 알린다.
        expect(server.sinceValues()).toEqual([0, 1, 2, 3]);
    });

    it("나눠 온 문장을 이어붙여 온전한 배열을 돌려준다", async () => {
        deltaServer(ALL, 3);

        const result = await runToCompletion(streamJobAudio("j", HEADERS, {})) as { sentences: { text: string }[] };

        expect(result.sentences.map((s) => s.text)).toEqual(["첫", "둘", "셋"]);
    });

    it("⚠️ 완료 응답의 전체 문장을 이어붙이지 않고 갈아끼운다", async () => {
        // 서버는 합성이 끝나면 타이밍을 다시 매긴 배열로 통째로 교체한다.
        // 그걸 델타로 착각해 이어붙이면 문장이 두 배가 되고, 하이라이트가
        // 문서 중간부터 전부 어긋난다.
        deltaServer(ALL, 2);

        const result = await runToCompletion(streamJobAudio("j", HEADERS, {})) as { sentences: { text: string }[] };

        expect(result.sentences).toHaveLength(3);
    });

    it("재생 가능해진 시점에도 그때까지 받은 문장을 모두 넘긴다", async () => {
        // 첫 청크를 트는 순간 그 구간의 하이라이트가 이미 맞아야 한다.
        deltaServer(ALL, 2);
        const handed: number[] = [];

        await runToCompletion(
            streamJobAudio("j", HEADERS, { onPlayable: (_blob, sentences) => handed.push(sentences.length) }),
        );

        expect(handed[handed.length - 1]).toBe(3);
    });
});
