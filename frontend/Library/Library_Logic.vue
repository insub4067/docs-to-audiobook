<script lang="ts">
import type { LibraryState, LibraryItem, LibraryPart } from "./Library_State.vue";
import type { ReaderLogic } from "../Reader/Reader_Logic.vue";
import type { RepeatMode } from "../Reader/ReaderControls/ReaderControls_State.vue";
import { useAuthLogic } from "../Auth/Auth_Logic.vue";
import { useToastLogic } from "../components/Toast/Toast_Logic.vue";
import { useToastState } from "../components/Toast/Toast_State.vue";
import { needsFreshSignedUrls } from "../services/signedUrls";

/** 목록 카드에 보여줄 청취 상태. 재생 이력이 없으면 null. */
export interface LibraryProgress {
    percent: number;
    isFinished: boolean;
    remainingLabel: string;
}

export interface LibraryLogic {
    loadLibrary(): Promise<void>;
    loadSaves(): Promise<void>;
    loadPlaybackPositions(): Promise<void>;
    getProgress(item: LibraryItem): LibraryProgress | null;
    selectCategory(category: string | null): void;
    openDetail(item: LibraryItem): void;
    closeDetail(): void;
    isSaved(item: LibraryItem): boolean;
    toggleSave(item: LibraryItem): Promise<void>;
    share(item: LibraryItem): Promise<void>;
    loadSentences(item: LibraryItem): Promise<unknown[]>;
    getLastPosition(item: LibraryItem): Promise<number>;
    playFromStart(item: LibraryItem): Promise<void>;
    playFromLastPosition(item: LibraryItem): Promise<void>;
    playFromChapter(item: LibraryItem, sentences: unknown[], startSeconds: number): void;
    /** 시리즈의 특정 부를 재생한다. 목차에서 부를 눌렀을 때. */
    playPart(work: LibraryItem, parts: LibraryPart[], index: number): Promise<void>;
    /** 지금 큐의 index번째 부를 재생한다. 재생목록 시트와 미니 플레이어
     *  스와이프가 쓴다(playlistNavigation.ts). */
    playQueuePartAt(index: number, options?: { openReaderUI?: boolean }): void;
}

export function useLibraryLogic(state: LibraryState, readerLogic: ReaderLogic): LibraryLogic {
    const authLogic = useAuthLogic();
    const { showToast } = useToastLogic(useToastState());

    async function loadLibrary(): Promise<void> {
        try {
            const response = await fetch("/api/library");
            if (response.ok) {
                const data = await response.json();
                state.items.value = data.library || [];
                state.fetchedAt.value = Date.now();
            }
        } catch (error) {
            console.error("라이브러리를 불러오지 못했습니다:", error);
        } finally {
            state.loaded.value = true;
        }
    }

    async function loadSaves(): Promise<void> {
        if (!authLogic.isLoggedIn()) {
            state.savedIds.value = new Set();
            state.savedItems.value = [];
            return;
        }
        try {
            const response = await fetch("/api/library/saves", { headers: authLogic.authHeaders() });
            if (response.ok) {
                const data = await response.json();
                const items: LibraryItem[] = data.library || [];
                state.savedItems.value = items;
                state.savedIds.value = new Set(items.map((item) => item.id));
            }
        } catch (error) {
            console.error("내 서재 목록을 불러오지 못했습니다:", error);
        }
    }

    async function loadPlaybackPositions(): Promise<void> {
        if (!authLogic.isLoggedIn()) {
            state.playbackSeconds.value = {};
            return;
        }
        try {
            const response = await fetch("/api/library/playback", { headers: authLogic.authHeaders() });
            if (response.ok) {
                const data = await response.json();
                state.playbackSeconds.value = data.positions || {};
            }
        } catch (error) {
            console.error("재생 위치를 불러오지 못했습니다:", error);
        }
    }

    // 끝까지 들어도 마지막 몇 초는 안 채워지는 경우가 흔하다(문장 끝에서
    // 멈추거나, 저장이 30초 간격이라). 97%를 넘으면 다 들은 것으로 본다.
    const FINISHED_RATIO = 0.97;

    function getProgress(item: LibraryItem): LibraryProgress | null {
        const seconds = state.playbackSeconds.value[item.id];
        const total = item.duration_seconds;
        if (!seconds || !total) return null;

        const ratio = Math.min(seconds / total, 1);
        const remainingMinutes = Math.round((total - seconds) / 60);
        return {
            percent: Math.round(ratio * 100),
            isFinished: ratio >= FINISHED_RATIO,
            remainingLabel: remainingMinutes > 0 ? `약 ${remainingMinutes}분 남음` : "1분 미만 남음",
        };
    }

    function selectCategory(category: string | null): void {
        state.activeCategory.value = category;
    }

    /** 상세 응답에서 부 목록을 받아 온다. 단권이면 빈 배열이 온다. */
    async function fetchParts(item: LibraryItem): Promise<LibraryPart[]> {
        try {
            const response = await fetch(`/api/library/${item.id}`);
            if (!response.ok) return [];
            const data = await response.json();
            return (data.parts || []) as LibraryPart[];
        } catch (error) {
            console.error("작품의 부 목록을 불러오지 못했습니다:", error);
            return [];
        }
    }

    function openDetail(item: LibraryItem): void {
        state.detailItem.value = item;
        state.isDetailOpen.value = true;
        state.detailParts.value = [];
        // 단권은 받아 올 부가 없다. 목록 응답의 part_count로 미리 알 수 있어
        // 대부분의 작품에서 요청 한 번을 아낀다.
        if ((item.part_count ?? 1) <= 1) return;

        state.isLoadingParts.value = true;
        void fetchParts(item).then((parts) => {
            // 받아 오는 사이에 다른 작품 상세로 갈아탔으면 버린다. 안 그러면
            // 방금 연 작품에 이전 작품의 목차가 붙는다.
            if (state.detailItem.value?.id !== item.id) return;
            state.detailParts.value = parts;
            state.isLoadingParts.value = false;
        });
    }

    function closeDetail(): void {
        state.isDetailOpen.value = false;
    }

    async function share(item: LibraryItem): Promise<void> {
        const url = `${window.location.origin}/?library=${item.id}`;
        const text = item.library_description
            ? `${item.title} — ${item.library_description}`
            : item.title;

        // 모바일에서는 OS 공유 시트가 열린다. 사용자가 시트를 그냥 닫으면
        // AbortError가 나는데, 이건 실패가 아니라 취소라 조용히 넘어간다.
        if (navigator.share) {
            try {
                await navigator.share({ title: item.title, text, url });
                return;
            } catch (error) {
                if ((error as Error)?.name === "AbortError") return;
                // 공유 시트가 열리지 못했으면 아래 클립보드 경로로 떨어진다.
            }
        }

        try {
            await navigator.clipboard.writeText(url);
            showToast("링크를 복사했어요", "success");
        } catch (error) {
            console.error("공유에 실패했습니다:", error);
            showToast("링크를 복사하지 못했습니다.", "error");
        }
    }

    function isSaved(item: LibraryItem): boolean {
        return state.savedIds.value.has(item.id);
    }

    async function toggleSave(item: LibraryItem): Promise<void> {
        if (!authLogic.isLoggedIn()) {
            showToast("내 서재 추가는 로그인 후 이용할 수 있습니다.", "info");
            return;
        }
        const saved = isSaved(item);
        try {
            const response = await fetch(`/api/library/${item.id}/save`, {
                method: saved ? "DELETE" : "POST",
                headers: authLogic.authHeaders(),
            });
            if (!response.ok) throw new Error("요청에 실패했습니다.");
            const next = new Set(state.savedIds.value);
            if (saved) next.delete(item.id);
            else next.add(item.id);
            state.savedIds.value = next;
            showToast(saved ? "내 서재에서 제거했어요" : "내 서재에 추가했어요", "success");
        } catch (error) {
            console.error(error);
            showToast("내 서재 변경에 실패했습니다.", "error");
        }
    }

    async function fetchSentences(item: LibraryItem): Promise<unknown[]> {
        if (!item.sentences_url) return [];
        try {
            const response = await fetch(item.sentences_url);
            if (response.ok) return await response.json();
        } catch (error) {
            console.error("작품 문장 데이터를 불러오지 못했습니다:", error);
        }
        return [];
    }

    async function fetchLastPosition(item: LibraryItem): Promise<number> {
        if (!authLogic.isLoggedIn()) return 0;
        try {
            const response = await fetch(`/api/audiobooks/${item.id}/playback`, { headers: authLogic.authHeaders() });
            if (!response.ok) return 0;
            const data = await response.json();
            return data.current_time_seconds || 0;
        } catch (error) {
            console.error("재생 위치를 불러오지 못했습니다:", error);
            return 0;
        }
    }

    /** 서명 URL이 만료될 때가 됐으면 목록을 다시 받아 같은 작품의 새 URL을
     *  돌려준다. 목록에서 사라진 작품이면 null.
     *  라이브러리는 탭을 열 때마다 갱신해서 뉴스보다 덜 노출되지만, 한 화면에
     *  한 시간 넘게 머물다 재생을 누르면 똑같이 죽은 URL을 쓰게 된다. */
    async function withFreshSignedUrls(item: LibraryItem): Promise<LibraryItem | null> {
        if (!needsFreshSignedUrls(state.fetchedAt.value)) return item;
        await loadLibrary();
        return state.items.value.find((candidate) => candidate.id === item.id) ?? null;
    }

    // ── 시리즈 재생목록 ─────────────────────────────────────────────────
    //
    // 뉴스 재생목록(News_Logic)과 구조가 거의 같다. 공용 모듈로 뽑지 않은
    // 이유는 뉴스가 매일 도는 기능이고, 거기에는 백그라운드 자동재생 차단을
    // 피하려고 다듬은 처리(동기 onEnded, 다음 항목 미리받기)가 들어 있기
    // 때문이다. 라이브러리 재생이 실사용으로 검증된 뒤에 합치는 게 낫다.
    //
    // 뉴스와 다른 점이 하나 있다. 뉴스는 "전체 듣기"로 시작했을 때만 다음
    // 기사로 넘어가지만(isContinuous), 시리즈는 어느 부에서 시작했든 항상
    // 다음 부로 이어진다. 책의 다음 장이 자동으로 이어지는 게 당연하고,
    // 낱개 기사와 달리 부는 그 자체로 완결된 항목이 아니기 때문이다.

    function partDisplayTitle(work: LibraryItem, part: LibraryPart): string {
        return part.part_title ? `${work.title} · ${part.part_title}` : work.title;
    }

    async function fetchPartSentences(part: LibraryPart): Promise<unknown[]> {
        if (!part.sentences_url) return [];
        try {
            const response = await fetch(part.sentences_url);
            if (response.ok) return await response.json();
        } catch (error) {
            console.error("부의 문장 데이터를 불러오지 못했습니다:", error);
        }
        return [];
    }

    /** 큐의 서명 URL이 만료될 때가 됐으면 상세를 다시 받아 갱신한다.
     *  24부짜리는 다 듣는 데 몇 시간이 걸려 1시간짜리 URL이 도중에 죽는다. */
    async function freshQueueParts(work: LibraryItem): Promise<LibraryPart[]> {
        if (!needsFreshSignedUrls(state.queueFetchedAt.value)) return state.queueParts.value;
        const parts = await fetchParts(work);
        if (!parts.length) return state.queueParts.value;
        state.queueParts.value = parts;
        state.queueFetchedAt.value = Date.now();
        return parts;
    }

    function openPartPrepared(
        work: LibraryItem, parts: LibraryPart[], index: number,
        part: LibraryPart, sentences: unknown[],
        options: { openReaderUI?: boolean; resumeSeconds?: number } = {},
    ): void {
        state.queueWork.value = work;
        state.queueParts.value = parts;
        state.queueIndex.value = index;

        readerLogic.openSharedReaderMode(
            partDisplayTitle(work, part), sentences as never, part.audio_url,
            {
                audiobookId: part.id,
                playlistKind: "library",
                onEnded: onQueueEnded,
                resumeSeconds: options.resumeSeconds ?? 0,
                openReaderUI: options.openReaderUI ?? true,
            },
        );
        state.isDetailOpen.value = false;
        // 지금 부를 트는 즉시 다음 부를 받아 둔다. 실패해도 조용히 넘어가고,
        // 그때는 ended에서 네트워크를 타는 경로로 떨어진다.
        void prepareNextPart(index);
    }

    async function playPart(work: LibraryItem, parts: LibraryPart[], index: number): Promise<void> {
        const part = parts[index];
        if (!part) return;
        state.queueFetchedAt.value = state.queueFetchedAt.value || Date.now();
        openPartPrepared(work, parts, index, part, await fetchPartSentences(part));
    }

    /** 다음에 재생될 부를 미리 받아 둔다. 목록 끝이면 처음으로 돌아간다
     *  ("전체 반복"이 그렇게 돌기 때문에 둘 다 이걸로 덮인다). */
    async function prepareNextPart(currentIndex: number): Promise<void> {
        const work = state.queueWork.value;
        if (!work || currentIndex < 0 || state.queueParts.value.length < 2) return;
        try {
            const parts = await freshQueueParts(work);
            const next = parts[(currentIndex + 1) % parts.length];
            if (!next || state.prefetchedNextPart.value?.id === next.id) return;
            state.prefetchedNextPart.value = {
                id: next.id, part: next, sentences: await fetchPartSentences(next),
            };
        } catch {
            state.prefetchedNextPart.value = null;
        }
    }

    function takePrefetchedPart(id: string) {
        const ready = state.prefetchedNextPart.value;
        if (!ready || ready.id !== id) return null;
        state.prefetchedNextPart.value = null;
        return ready;
    }

    /** 미리 받아 뒀으면 네트워크 없이 곧바로 튼다. */
    function playNextPart(index: number, options: { openReaderUI?: boolean } = {}): void {
        const work = state.queueWork.value;
        const parts = state.queueParts.value;
        const part = parts[index];
        if (!work || !part) return;

        const ready = takePrefetchedPart(part.id);
        if (ready) {
            openPartPrepared(work, parts, index, ready.part, ready.sentences,
                { openReaderUI: options.openReaderUI ?? false });
            return;
        }
        void fetchPartSentences(part).then((sentences) => {
            openPartPrepared(work, parts, index, part, sentences,
                { openReaderUI: options.openReaderUI ?? false });
        });
    }

    /** ⚠️ 동기 함수다. await를 하나라도 끼우면 백그라운드에서 다음 부가
     *  이어지지 않는다 — ended에서 멀어진 play()는 자동재생으로 막힌다.
     *  (News_Logic.onQueueEnded와 같은 제약이다.) */
    function onQueueEnded(repeatMode: RepeatMode = "off"): void {
        const parts = state.queueParts.value;
        const current = state.queueIndex.value;
        if (current < 0 || parts.length === 0) return;

        if (repeatMode === "all") {
            playNextPart((current + 1) % parts.length);
            return;
        }
        if (current + 1 < parts.length) {
            playNextPart(current + 1);
            return;
        }
        state.queueIndex.value = -1;
        state.prefetchedNextPart.value = null;
        showToast(`${state.queueWork.value?.title ?? "작품"}을 모두 들었어요`, "success");
    }

    async function playFromStart(item: LibraryItem): Promise<void> {
        const fresh = await withFreshSignedUrls(item);
        if (!fresh) {
            showToast("이 작품은 더 이상 제공되지 않습니다.", "error");
            return;
        }

        // 시리즈면 1부부터 재생목록으로 튼다. 상세를 거치지 않고 목록 카드에서
        // 바로 누른 경우라 부 목록이 아직 없을 수 있어 여기서 받아 온다.
        if ((fresh.part_count ?? 1) > 1) {
            const parts = state.detailParts.value.length && state.detailItem.value?.id === fresh.id
                ? state.detailParts.value
                : await fetchParts(fresh);
            if (parts.length) {
                state.queueFetchedAt.value = Date.now();
                await playPart(fresh, parts, 0);
                return;
            }
            // 부를 못 받았으면 아래 단권 경로로 떨어진다 — 1부만이라도 들린다.
        }

        const sentences = await fetchSentences(fresh);
        readerLogic.openSharedReaderMode(fresh.title, sentences as never, fresh.audio_url, { audiobookId: fresh.id });
        state.isDetailOpen.value = false;
    }

    async function playFromLastPosition(item: LibraryItem): Promise<void> {
        const fresh = await withFreshSignedUrls(item);
        if (!fresh) {
            showToast("이 작품은 더 이상 제공되지 않습니다.", "error");
            return;
        }

        // ⚠️ 시리즈에서 작품 id로 이어 들으면 언제나 1부로 돌아간다. 작품
        // id는 곧 1부의 id이기 때문이다. 재생 위치는 부마다 따로 저장되므로
        // (playback_history가 audiobook_id 단위) 실제로 듣던 부를 찾아야 한다.
        if ((fresh.part_count ?? 1) > 1) {
            const parts = state.detailParts.value.length && state.detailItem.value?.id === fresh.id
                ? state.detailParts.value
                : await fetchParts(fresh);
            // 기록이 남은 부 중 가장 뒤엣것이 마지막으로 듣던 자리다.
            const lastIndex = parts.reduce(
                (found, part, index) => (state.playbackSeconds.value[part.id] ? index : found), -1);
            if (lastIndex >= 0) {
                const part = parts[lastIndex];
                state.queueFetchedAt.value = Date.now();
                openPartPrepared(fresh, parts, lastIndex, part, await fetchPartSentences(part),
                    { resumeSeconds: state.playbackSeconds.value[part.id] });
                return;
            }
            if (parts.length) {
                state.queueFetchedAt.value = Date.now();
                await playPart(fresh, parts, 0);
                return;
            }
        }

        const [sentences, resumeSeconds] = await Promise.all([fetchSentences(fresh), fetchLastPosition(fresh)]);
        readerLogic.openSharedReaderMode(fresh.title, sentences as never, fresh.audio_url, { audiobookId: fresh.id, resumeSeconds });
        state.isDetailOpen.value = false;
    }

    // 목차에서 특정 장을 고르는 것도 결국 "그 장이 시작하는 지점부터
    // 이어 듣기"와 같아서 resumeSeconds를 재사용한다.
    function playFromChapter(item: LibraryItem, sentences: unknown[], startSeconds: number): void {
        readerLogic.openSharedReaderMode(item.title, sentences as never, item.audio_url, { audiobookId: item.id, resumeSeconds: startSeconds });
        state.isDetailOpen.value = false;
    }

    return {
        loadLibrary, loadSaves, loadPlaybackPositions, getProgress,
        selectCategory, openDetail, closeDetail, isSaved, toggleSave, share,
        loadSentences: fetchSentences, getLastPosition: fetchLastPosition,
        playFromStart, playFromLastPosition, playFromChapter,
        playPart, playQueuePartAt: playNextPart,
    };
}

export default {};
</script>
