<script lang="ts">
import type { NewsState, NewsItem } from "./News_State.vue";
import type { ReaderLogic } from "../../Reader/Reader_Logic.vue";
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

    // queueIndex >= 0이면 "전체 듣기" 중이라는 뜻 — 오디오가 끝나면 다음
    // 항목으로 자동 진행한다. 개별 항목을 그냥 눌러서 열 때는 -1(큐 없음).
    async function openNewsItem(item: NewsItem, queueIndex = -1): Promise<void> {
        state.queueIndex.value = queueIndex;
        const sentences = await fetchSentences(item);
        readerLogic.openSharedReaderMode(
            item.title,
            sentences as never,
            item.audio_url,
            null,
            queueIndex >= 0 ? onQueueEnded : undefined,
        );
        state.isListOpen.value = false;
    }

    async function onQueueEnded(): Promise<void> {
        const nextIndex = state.queueIndex.value + 1;
        const next = state.items.value[nextIndex];
        if (next) {
            await openNewsItem(next, nextIndex);
        } else {
            state.queueIndex.value = -1;
            showToast("경제 뉴스를 모두 들었어요", "success");
        }
    }

    async function playAll(): Promise<void> {
        const first = state.items.value[0];
        if (first) await openNewsItem(first, 0);
    }

    return { loadNews, openList, closeList, openNewsItem, playAll };
}

export default {};
</script>
