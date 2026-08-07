<script lang="ts">
import { ref, type Ref } from "vue";

export interface LibraryItem {
    id: string;
    title: string;
    library_category: string | null;
    library_edition: string | null;
    library_translator: string | null;
    library_source: string | null;
    library_rights: string | null;
    library_description: string | null;
    library_chapter_count: number | null;
    duration_seconds: number | null;
    created_at: string;
    audio_url: string;
    sentences_url: string | null;
}

export type LibrarySortKey = "recent" | "duration-asc" | "duration-desc" | "listening";

export interface LibraryState {
    items: Ref<LibraryItem[]>;
    loaded: Ref<boolean>;
    // 목록의 audio_url/sentences_url은 1시간짜리 서명 URL이다
    // (services/signedUrls.ts). 언제 받아 왔는지 알아야 만료 전에 갱신한다.
    fetchedAt: Ref<number>;
    savedIds: Ref<Set<string>>;
    savedItems: Ref<LibraryItem[]>;
    activeCategory: Ref<string | null>;
    searchQuery: Ref<string>;
    sortKey: Ref<LibrarySortKey>;
    detailItem: Ref<LibraryItem | null>;
    isDetailOpen: Ref<boolean>;
    /** audiobook_id → 마지막 재생 위치(초). 목록 카드의 진행률에 쓴다. */
    playbackSeconds: Ref<Record<string, number>>;
}

const state: LibraryState = {
    items: ref([]),
    loaded: ref(false),
    fetchedAt: ref(0),
    savedIds: ref(new Set()),
    savedItems: ref([]),
    activeCategory: ref(null),
    searchQuery: ref(""),
    sortKey: ref("recent"),
    detailItem: ref(null),
    isDetailOpen: ref(false),
    playbackSeconds: ref({}),
};

export function useLibraryState(): LibraryState {
    return state;
}

export default {};
</script>
