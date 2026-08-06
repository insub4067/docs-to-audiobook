<script lang="ts">
import type { LibraryState, LibraryItem } from "./Library_State.vue";
import type { ReaderLogic } from "../Reader/Reader_Logic.vue";
import { useAuthLogic } from "../Auth/Auth_Logic.vue";
import { useToastLogic } from "../components/Toast/Toast_Logic.vue";
import { useToastState } from "../components/Toast/Toast_State.vue";

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
    loadSentences(item: LibraryItem): Promise<unknown[]>;
    getLastPosition(item: LibraryItem): Promise<number>;
    playFromStart(item: LibraryItem): Promise<void>;
    playFromLastPosition(item: LibraryItem): Promise<void>;
    playFromChapter(item: LibraryItem, sentences: unknown[], startSeconds: number): void;
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

    function openDetail(item: LibraryItem): void {
        state.detailItem.value = item;
        state.isDetailOpen.value = true;
    }

    function closeDetail(): void {
        state.isDetailOpen.value = false;
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

    async function playFromStart(item: LibraryItem): Promise<void> {
        const sentences = await fetchSentences(item);
        readerLogic.openSharedReaderMode(item.title, sentences as never, item.audio_url, { audiobookId: item.id });
        state.isDetailOpen.value = false;
    }

    async function playFromLastPosition(item: LibraryItem): Promise<void> {
        const [sentences, resumeSeconds] = await Promise.all([fetchSentences(item), fetchLastPosition(item)]);
        readerLogic.openSharedReaderMode(item.title, sentences as never, item.audio_url, { audiobookId: item.id, resumeSeconds });
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
        selectCategory, openDetail, closeDetail, isSaved, toggleSave,
        loadSentences: fetchSentences, getLastPosition: fetchLastPosition,
        playFromStart, playFromLastPosition, playFromChapter,
    };
}

export default {};
</script>
