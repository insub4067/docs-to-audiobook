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
    // IndexedDB에서 오지만 첫 진입에는 비어 있다. 이 값이 false인 동안
    // "아직 생성된 책이 없습니다"를 띄우면 잠깐 거짓말을 하게 된다.
    loaded: Ref<boolean>;
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
        loaded: ref(false),
        actionSheetTarget: ref(null),
        isActionSheetOpen: ref(false),
        backgroundJobItems: ref([]),
    };
}

export default {};
</script>
