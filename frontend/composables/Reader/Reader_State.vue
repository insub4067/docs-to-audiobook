<script lang="ts">
import { ref, type Ref } from "vue";
import type { AudiobookRecord } from "../../services/indexedDb";
import type { ReaderDisplayItem, HeadingRef } from "./sentenceDisplay";

export interface ReaderState {
    isOpen: Ref<boolean>;
    title: Ref<string>;
    displayItems: Ref<ReaderDisplayItem[]>;
    headings: Ref<HeadingRef[]>;
    activeIndex: Ref<number>;
    currentTimeLabel: Ref<string>;
    durationLabel: Ref<string>;
    progressPercent: Ref<number>;
    isPlaying: Ref<boolean>;
    showShareBtn: Ref<boolean>;
    showSaveSharedBtn: Ref<boolean>;
    isIndexSheetOpen: Ref<boolean>;
    currentAudioObject: Ref<AudiobookRecord | null>;
    audioEl: Ref<HTMLAudioElement | null>;
    contentEl: Ref<HTMLElement | null>;
}

export function useReaderState(): ReaderState {
    return {
        isOpen: ref(false),
        title: ref(""),
        displayItems: ref([]),
        headings: ref([]),
        activeIndex: ref(-1),
        currentTimeLabel: ref("00:00"),
        durationLabel: ref("00:00"),
        progressPercent: ref(0),
        isPlaying: ref(false),
        showShareBtn: ref(false),
        showSaveSharedBtn: ref(false),
        isIndexSheetOpen: ref(false),
        currentAudioObject: ref(null),
        audioEl: ref(null),
        contentEl: ref(null),
    };
}

export default {};
</script>
