// 합성이 끝나기 전에 앞 구간부터 받아 재생할 수 있게 하는 클라이언트 쪽.
//
// 10만 자 문서는 합성이 다 끝나는 데 70초 넘게 걸리지만 첫 청크는 2초면
// 나오고, 그 하나가 100초 안팎의 오디오다. 그동안 사용자는 빈 화면을 봤다.
//
// ⚠️ 설계에서 제일 중요한 결정: 청크를 각각 재생하지 않고 **받은 청크를 모아
// 매번 하나의 Blob으로 다시 만든다.** MP3는 이어 붙이면 그대로 재생되므로,
// 이 Blob은 언제나 0초에서 시작하는 온전한 파일이다. 그래서 읽기 화면의
// el.currentTime이 계속 "문서 전체 기준 시각"으로 남는다 — 문장 하이라이트,
// 장 이동, 이어듣기, 진행바까지 19곳이 그 가정 위에 있는데 한 줄도 건드리지
// 않아도 된다. 청크별로 따로 재생했다면 그 전부에 좌표 변환이 필요했다.
//
// 부수 효과로 완료 후 전체 파일을 다시 받을 필요도 없어졌다. 모아 둔 Blob이
// 서버가 합친 파일과 바이트 단위로 같기 때문이다(합성 쪽에서 그걸 테스트로
// 고정해 뒀다). 10만 자 문서 기준 수십 MB를 아낀다.
import type { ReaderSentence } from "../Reader/sentenceDisplay";

export interface JobHeadings {
    text: string;
    level: number;
    sentIndex: number;
    startMs: number;
}

export interface ProgressiveResult {
    blob: Blob;
    sentences: ReaderSentence[];
    headings: JobHeadings[];
    displayMarkdown: string;
}

export interface ProgressiveHandlers {
    /** 청크가 새로 붙을 때마다. blob은 항상 0초부터 시작하는 온전한 MP3다. */
    onPlayable?(blob: Blob, sentences: ReaderSentence[]): void;
    onProgress?(completedChunks: number, totalChunks: number): void;
}

const POLL_INTERVAL_MS = 2000;

function delay(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

/** 작업이 끝날 때까지 폴링하면서, 준비되는 청크를 순서대로 받아 모은다. */
export async function streamJobAudio(
    jobId: string,
    headers: Record<string, string>,
    handlers: ProgressiveHandlers = {},
): Promise<ProgressiveResult> {
    const parts: Blob[] = [];

    async function fetchReadyChunks(readyChunks: number): Promise<boolean> {
        let added = false;
        while (parts.length < readyChunks) {
            const response = await fetch(`/api/job/${jobId}/chunk/${parts.length}`, { headers });
            if (!response.ok) {
                // 합성이 끝나면 청크 파일은 지워지고 합본만 남는다. 그 찰나에
                // 요청이 겹치면 404가 난다 — 다음 폴링에서 completed를 보고
                // 합본으로 받아 가면 되므로 여기서는 조용히 멈춘다.
                return added;
            }
            parts.push(await response.blob());
            added = true;
        }
        return added;
    }

    for (;;) {
        const response = await fetch(`/api/job/${jobId}`, { headers });
        if (!response.ok) throw new Error("작업 상태 통신 실패");
        const job = await response.json();

        if (job.status === "error") throw new Error(job.error || "서버 오디오 변환 에러 발생");
        if (job.status !== "processing" && job.status !== "completed") {
            throw new Error("알 수 없는 작업 상태입니다.");
        }

        handlers.onProgress?.(Number(job.completed_chunks) || 0, Number(job.total_chunks) || 0);

        const grew = await fetchReadyChunks(Number(job.ready_chunks) || 0);
        if (grew) handlers.onPlayable?.(new Blob(parts, { type: "audio/mpeg" }), job.sentences || []);

        if (job.status === "completed") {
            // 청크를 다 받아 뒀으면 합본을 다시 받지 않는다. 두 결과물은
            // 바이트 단위로 같다(backend/tests/test_progressive_chunks.py).
            const total = Number(job.total_chunks) || 0;
            const blob = parts.length > 0 && parts.length >= total
                ? new Blob(parts, { type: "audio/mpeg" })
                : await downloadWholeAudio(job.audio_url, headers);
            return {
                blob,
                sentences: job.sentences || [],
                headings: job.headings || [],
                displayMarkdown: job.display_markdown || "",
            };
        }

        await delay(POLL_INTERVAL_MS);
    }
}

async function downloadWholeAudio(audioUrl: string, headers: Record<string, string>): Promise<Blob> {
    const response = await fetch(audioUrl, { headers });
    if (!response.ok) throw new Error("오디오 파일 다운로드 실패");
    return await response.blob();
}
