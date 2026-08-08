<script lang="ts">
import { ref, type Ref } from "vue";
import type { AudiobookRecord } from "../services/indexedDb";
import type { ReaderDisplayItem, HeadingRef } from "./sentenceDisplay";
import type { BookmarkRecord } from "../services/bookmarks";

export interface ReaderState {
    isOpen: Ref<boolean>;
    title: Ref<string>;
    displayItems: Ref<ReaderDisplayItem[]>;
    headings: Ref<HeadingRef[]>;
    activeIndex: Ref<number>;
    isScrolledAway: Ref<boolean>;
    /** 벗어난 활성 문장이 화면 아래쪽에 있는가. "현재 위치로" 화살표 방향이 이 값에서 나온다. */
    isCurrentBelow: Ref<boolean>;
    currentTimeLabel: Ref<string>;
    durationLabel: Ref<string>;
    /** 총 재생시간(초). 마지막 장의 길이를 계산하려면 숫자가 필요하다. */
    durationSeconds: Ref<number>;
    progressPercent: Ref<number>;
    isPlaying: Ref<boolean>;
    showShareBtn: Ref<boolean>;
    showSaveSharedBtn: Ref<boolean>;
    isIndexSheetOpen: Ref<boolean>;
    isMoreSheetOpen: Ref<boolean>;
    isSettingsSheetOpen: Ref<boolean>;
    isPlaylistSheetOpen: Ref<boolean>;
    isBookmarkSheetOpen: Ref<boolean>;
    bookmarks: Ref<BookmarkRecord[]>;
    sharedPlaylistKind: Ref<"news" | null>;
    currentAudioObject: Ref<AudiobookRecord | null>;
    audioEl: Ref<HTMLAudioElement | null>;
    contentEl: Ref<HTMLElement | null>;
    containerEl: Ref<HTMLElement | null>;
}

export function useReaderState(): ReaderState {
    return {
        isOpen: ref(false),
        title: ref(""),
        displayItems: ref([]),
        headings: ref([]),
        activeIndex: ref(-1),
        isScrolledAway: ref(false),
        isCurrentBelow: ref(false),
        currentTimeLabel: ref("00:00"),
        durationLabel: ref("00:00"),
        durationSeconds: ref(0),
        progressPercent: ref(0),
        isPlaying: ref(false),
        showShareBtn: ref(false),
        showSaveSharedBtn: ref(false),
        isIndexSheetOpen: ref(false),
        isMoreSheetOpen: ref(false),
        isSettingsSheetOpen: ref(false),
        isPlaylistSheetOpen: ref(false),
        isBookmarkSheetOpen: ref(false),
        bookmarks: ref([]),
        sharedPlaylistKind: ref(null),
        currentAudioObject: ref(null),
        audioEl: ref(null),
        contentEl: ref(null),
        containerEl: ref(null),
    };
}

export default {};
</script>
