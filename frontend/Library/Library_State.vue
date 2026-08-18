<script lang="ts">
import { ref, type Ref } from "vue";

/** 여러 부로 나뉜 작품의 한 부. 상세 응답의 parts에 번호순으로 들어 있다. */
export interface LibraryPart {
    id: string;
    part_number: number | null;
    part_title: string;
    duration_seconds: number | null;
    audio_url: string;
    sentences_url: string | null;
}

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
    /** 부 수. 단권은 1이라 화면이 시리즈와 단권을 갈라 처리하지 않아도 된다. */
    part_count?: number;
    /** 작품 전체 재생시간(모든 부의 합). 단권은 duration_seconds와 같다. */
    total_duration_seconds?: number;
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

    // ── 시리즈(부로 나뉜 작품) ──────────────────────────────────────────
    /** 지금 열려 있는 상세의 부 목록. 단권이면 빈 배열. */
    detailParts: Ref<LibraryPart[]>;
    isLoadingParts: Ref<boolean>;
    /** 재생 중인 작품의 부 목록. 상세를 닫아도 재생목록은 남아야 해서
     *  detailParts와 따로 둔다 — 상세에서 튼 뒤 다른 작품 상세를 열면
     *  detailParts는 갈리지만 지금 듣고 있는 큐는 그대로여야 한다. */
    queueParts: Ref<LibraryPart[]>;
    /** 재생 중인 부가 큐에서 몇 번째인가. 재생 중이 아니면 -1. */
    queueIndex: Ref<number>;
    /** 큐가 속한 작품(제목 표시와 부 이동에 쓴다). */
    queueWork: Ref<LibraryItem | null>;
    /** 큐의 서명 URL을 언제 받았나. 24부짜리는 재생에 몇 시간이 걸려
     *  1시간짜리 서명 URL이 도중에 죽는다 — 다음 부를 미리 받을 때
     *  이 시각을 보고 갱신한다(services/signedUrls.ts). */
    queueFetchedAt: Ref<number>;
    /** 다음 부를 미리 받아 둔 것. ⚠️ 이게 없으면 화면이 꺼져 있는 동안
     *  다음 부로 이어지지 않는다 — ended 안에서 네트워크를 타면 그 사이에
     *  실행이 밀리고, 새 소스에 대한 play()가 자동재생으로 막힌다.
     *  News_State.prefetchedNext와 같은 이유다. */
    prefetchedNextPart: Ref<{ id: string; part: LibraryPart; sentences: unknown[] } | null>;
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
    detailParts: ref([]),
    isLoadingParts: ref(false),
    queueParts: ref([]),
    queueIndex: ref(-1),
    queueWork: ref(null),
    queueFetchedAt: ref(0),
    prefetchedNextPart: ref(null),
};

export function useLibraryState(): LibraryState {
    return state;
}

export default {};
</script>
