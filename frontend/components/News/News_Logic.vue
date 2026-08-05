<script lang="ts">
import type { NewsState, NewsItem } from "./News_State.vue";
import type { ReaderLogic } from "../../Reader/Reader_Logic.vue";
import type { RepeatMode } from "../../Reader/ReaderControls/ReaderControls_State.vue";
import { useToastLogic } from "../Toast/Toast_Logic.vue";
import { useToastState } from "../Toast/Toast_State.vue";

export interface NewsLogic {
    loadNews(): Promise<void>;
    openList(): void;
    closeList(): void;
    openNewsItem(item: NewsItem, queueIndex?: number): Promise<void>;
    playAll(): Promise<void>;
}

export function useNewsLogic(state: NewsState, readerLogic: ReaderLogic): NewsLogic {
    const { showToast } = useToastLogic(useToastState());

    async function loadNews(): Promise<void> {
        try {
            const response = await fetch("/api/news");
            if (response.ok) {
                const data = await response.json();
                state.items.value = data.news || [];
            }
        } catch (error) {
            console.error("경제 뉴스를 불러오지 못했습니다:", error);
        } finally {
            state.loaded.value = true;
        }
    }

    function openList(): void {
        state.isListOpen.value = true;
    }

    function closeList(): void {
        state.isListOpen.value = false;
    }

    async function fetchSentences(item: NewsItem): Promise<unknown[]> {
        if (!item.sentences_url) return [];
        try {
            const response = await fetch(item.sentences_url);
            if (response.ok) return await response.json();
        } catch (error) {
            console.error("뉴스 문장 데이터를 불러오지 못했습니다:", error);
        }
        return [];
    }

    // queueIndex >= 0이면 "전체 듣기"로 시작한 연속 재생이라는 뜻. 개별 기사를
    // 눌러서 열 때(-1)도 목록에서의 위치는 기록해 둔다 — "전체 반복"은 어떻게
    // 재생을 시작했든 목록을 순환해야 하기 때문이다. 그래서 onEnded도 항상
    // 넘기고, 실제로 무엇을 할지는 onQueueEnded가 반복 모드를 보고 정한다.
    async function openNewsItem(item: NewsItem, queueIndex = -1): Promise<void> {
        state.isContinuous.value = queueIndex >= 0;
        state.queueIndex.value = queueIndex >= 0
            ? queueIndex
            : state.items.value.findIndex((candidate) => candidate.id === item.id);
        const sentences = await fetchSentences(item);
        readerLogic.openSharedReaderMode(item.title, sentences as never, item.audio_url, {
            onEnded: onQueueEnded,
            playlistKind: "news",
        });
        state.isListOpen.value = false;
    }

    async function onQueueEnded(repeatMode: RepeatMode = "off"): Promise<void> {
        const items = state.items.value;
        const current = state.queueIndex.value;
        if (current < 0 || items.length === 0) return;

        // "전체 반복"은 재생목록 전체를 반복하라는 뜻이다. 전체 듣기로
        // 시작했든 기사 하나를 눌러서 시작했든 목록을 끝까지 돌고 처음으로
        // 되돌아간다(한 기사만 되풀이하는 건 "현재 오디오 반복"이고, 그건
        // 리더가 큐를 거치지 않고 직접 처리한다).
        if (repeatMode === "all") {
            const nextIndex = (current + 1) % items.length;
            await openNewsItem(items[nextIndex], state.isContinuous.value ? nextIndex : -1);
            return;
        }

        // 반복이 꺼져 있으면 "전체 듣기"로 시작했을 때만 다음 기사로 넘어간다.
        if (!state.isContinuous.value) return;

        const next = items[current + 1];
        if (next) {
            await openNewsItem(next, current + 1);
            return;
        }
        state.queueIndex.value = -1;
        state.isContinuous.value = false;
        showToast("경제 뉴스를 모두 들었어요", "success");
    }

    async function playAll(): Promise<void> {
        const first = state.items.value[0];
        if (first) await openNewsItem(first, 0);
    }

    return { loadNews, openList, closeList, openNewsItem, playAll };
}

export default {};
</script>
