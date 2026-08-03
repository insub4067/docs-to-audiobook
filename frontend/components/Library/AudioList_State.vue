<script lang="ts">
import { ref, type Ref } from "vue";
import type { AudiobookRecord } from "../../services/indexedDb";

export interface BackgroundJobItem {
    jobId: string;
    title: string;
    folderId: string | null;
}

export interface AudioListState {
    savedAudiobooks: Ref<AudiobookRecord[]>;
    actionSheetTarget: Ref<AudiobookRecord | null>;
    isActionSheetOpen: Ref<boolean>;
    // 백그라운드(대용량) 생성 작업 — 알림 기능(notifications.js)이 페이지
    // 재방문 시 이어서 보여주는, Generation 화면의 generatingItems와는
    // 별개의 목록이다.
    backgroundJobItems: Ref<BackgroundJobItem[]>;
}

export function useAudioListState(): AudioListState {
    return {
        savedAudiobooks: ref([]),
        actionSheetTarget: ref(null),
        isActionSheetOpen: ref(false),
        backgroundJobItems: ref([]),
    };
}

export default {};
</script>
