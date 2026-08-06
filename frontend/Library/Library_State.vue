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

export interface LibraryState {
    items: Ref<LibraryItem[]>;
    loaded: Ref<boolean>;
    savedIds: Ref<Set<string>>;
    savedItems: Ref<LibraryItem[]>;
    activeCategory: Ref<string | null>;
    detailItem: Ref<LibraryItem | null>;
    isDetailOpen: Ref<boolean>;
    /** audiobook_id → 마지막 재생 위치(초). 목록 카드의 진행률에 쓴다. */
    playbackSeconds: Ref<Record<string, number>>;
}

const state: LibraryState = {
    items: ref([]),
    loaded: ref(false),
    savedIds: ref(new Set()),
    savedItems: ref([]),
    activeCategory: ref(null),
    detailItem: ref(null),
    isDetailOpen: ref(false),
    playbackSeconds: ref({}),
};

export function useLibraryState(): LibraryState {
    return state;
}

export default {};
</script>
