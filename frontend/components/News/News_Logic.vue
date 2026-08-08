<script lang="ts">
import type { NewsState, NewsItem } from "./News_State.vue";
import type { ReaderLogic } from "../../Reader/Reader_Logic.vue";
import type { RepeatMode } from "../../Reader/ReaderControls/ReaderControls_State.vue";
import { useToastLogic } from "../Toast/Toast_Logic.vue";
import { useToastState } from "../Toast/Toast_State.vue";
import { needsFreshSignedUrls } from "../../services/signedUrls";

export interface NewsLogic {
    loadNews(): Promise<void>;
    openList(): void;
    closeList(): void;
    openNewsItem(item: NewsItem, queueIndex?: number, options?: { openReaderUI?: boolean }): Promise<void>;
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
                state.fetchedAt.value = Date.now();
                // 목록이 갈렸으면 미리 받아 둔 다음 기사도 더 이상 유효하지 않다.
                state.prefetchedNext.value = null;
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

    /** 서명 URL이 만료될 때가 됐으면 목록을 다시 받아 같은 기사의 새 URL을
     *  돌려준다. 목록에서 사라진 기사면 null. */
    async function withFreshSignedUrls(item: NewsItem): Promise<NewsItem | null> {
        if (!needsFreshSignedUrls(state.fetchedAt.value)) return item;
        await loadNews();
        return state.items.value.find((candidate) => candidate.id === item.id) ?? null;
    }

    // queueIndex >= 0이면 "전체 듣기"로 시작한 연속 재생이라는 뜻. 개별 기사를
    // 눌러서 열 때(-1)도 목록에서의 위치는 기록해 둔다 — "전체 반복"은 어떻게
    // 재생을 시작했든 목록을 순환해야 하기 때문이다. 그래서 onEnded도 항상
    // 넘기고, 실제로 무엇을 할지는 onQueueEnded가 반복 모드를 보고 정한다.
    async function openNewsItem(item: NewsItem, queueIndex = -1, options: { openReaderUI?: boolean } = {}): Promise<void> {
        // ⚠️ 목록을 오래 들고 있었으면 이 항목의 서명 URL이 이미 죽어 있다.
        // 재생을 누른 시점에 갱신해, 오디오와 문장을 살아 있는 URL로 받는다.
        const fresh = await withFreshSignedUrls(item);
        if (!fresh) {
            showToast("이 기사는 더 이상 제공되지 않습니다.", "error");
            return;
        }
        openPrepared(fresh, await fetchSentences(fresh), queueIndex, options);
    }

    /** 이미 받아 둔 문장으로 연다. 네트워크를 타지 않으므로 ended 안에서
     *  그대로 불러도 되고, 그래야 백그라운드에서도 다음 곡이 이어진다. */
    function openPrepared(
        item: NewsItem, sentences: unknown[], queueIndex: number,
        options: { openReaderUI?: boolean } = {},
    ): void {
        // 위치 해석은 여기 한 곳에서만 한다. 두 군데로 갈리면 -1로 들어온
        // 경우(기사를 눌러서 연 경우)에 위치를 잃는다.
        state.isContinuous.value = queueIndex >= 0;
        state.queueIndex.value = queueIndex >= 0
            ? queueIndex
            : state.items.value.findIndex((candidate) => candidate.id === item.id);
        readerLogic.openSharedReaderMode(item.title, sentences as never, item.audio_url, {
            onEnded: onQueueEnded,
            playlistKind: "news",
            openReaderUI: options.openReaderUI ?? true,
        });
        state.isListOpen.value = false;
        // 지금 것을 트는 즉시 다음 것을 받아 둔다. 실패해도 조용히 넘어가고,
        // 그때는 예전처럼 ended에서 받아 오는 경로로 떨어진다.
        void prepareNext(state.queueIndex.value);
    }

    /** 다음에 재생될 기사를 미리 받아 둔다. 목록 끝이면 처음으로 돌아간다
     *  ("전체 반복"이 그렇게 돌기 때문에 둘 다 이걸로 덮인다).
     *
     *  ⚠️ 이게 없으면 PWA를 벗어난 동안 연속 재생이 멈춘다. 예전에는 ended
     *  안에서 서명 URL 갱신과 문장 데이터를 네트워크로 받은 뒤에야 play()를
     *  불렀는데, 화면이 백그라운드면 그 사이에 실행이 지연되고 새 소스에 대한
     *  play()는 자동재생으로 취급돼 막힌다. 미리 받아 두면 ended에서는
     *  네트워크 없이 src만 갈아 끼우면 된다. */
    async function prepareNext(currentIndex: number): Promise<void> {
        const items = state.items.value;
        if (currentIndex < 0 || items.length < 2) return;
        const next = items[(currentIndex + 1) % items.length];
        if (!next || state.prefetchedNext.value?.id === next.id) return;
        try {
            const fresh = await withFreshSignedUrls(next);
            if (!fresh) return;
            state.prefetchedNext.value = { id: fresh.id, item: fresh, sentences: await fetchSentences(fresh) };
        } catch {
            state.prefetchedNext.value = null;
        }
    }

    /** 미리 받아 둔 것이 이 기사면 꺼내 쓴다(한 번 쓰면 버린다).
     *
     *  요청하는 id는 언제나 "지금 목록"에서 뽑은 것이므로, id가 맞으면
     *  내용도 맞는다. 목록이 갈려 다음 기사가 달라졌으면 id가 어긋나
     *  자연히 무시된다. */
    function takePrefetched(id: string) {
        const ready = state.prefetchedNext.value;
        if (!ready || ready.id !== id) return null;
        state.prefetchedNext.value = null;
        return ready;
    }

    /** ⚠️ 동기 함수다. await를 하나라도 끼우면 백그라운드에서 다음 곡이
     *  이어지지 않는다 — ended에서 멀어진 play()는 자동재생으로 막힌다. */
    function onQueueEnded(repeatMode: RepeatMode = "off"): void {
        const items = state.items.value;
        const current = state.queueIndex.value;
        if (current < 0 || items.length === 0) return;

        // "전체 반복"은 재생목록 전체를 반복하라는 뜻이다. 전체 듣기로
        // 시작했든 기사 하나를 눌러서 시작했든 목록을 끝까지 돌고 처음으로
        // 되돌아간다(한 기사만 되풀이하는 건 "현재 오디오 반복"이고, 그건
        // 리더가 큐를 거치지 않고 직접 처리한다).
        if (repeatMode === "all") {
            const nextIndex = (current + 1) % items.length;
            playNext(items[nextIndex], state.isContinuous.value ? nextIndex : -1);
            return;
        }

        // 반복이 꺼져 있으면 "전체 듣기"로 시작했을 때만 다음 기사로 넘어간다.
        if (!state.isContinuous.value) return;

        const next = items[current + 1];
        if (next) {
            playNext(next, current + 1);
            return;
        }
        state.queueIndex.value = -1;
        state.isContinuous.value = false;
        showToast("경제 뉴스를 모두 들었어요", "success");
    }

    /** 미리 받아 뒀으면 네트워크 없이 곧바로 튼다. 없으면 예전 경로로
     *  떨어지는데, 그때는 백그라운드에서 끊길 수 있다. */
    function playNext(item: NewsItem, queueIndex: number): void {
        const ready = takePrefetched(item.id);
        if (ready) {
            openPrepared(ready.item, ready.sentences, queueIndex, { openReaderUI: false });
            return;
        }
        void openNewsItem(item, queueIndex, { openReaderUI: false });
    }

    async function playAll(): Promise<void> {
        const first = state.items.value[0];
        if (first) await openNewsItem(first, 0);
    }

    return { loadNews, openList, closeList, openNewsItem, playAll };
}

export default {};
</script>
