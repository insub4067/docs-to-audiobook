<script lang="ts">
import { ref, type Ref } from "vue";
import type { AudiobookRecord } from "../../services/indexedDb";
import type { ReaderSentence } from "../../Reader/sentenceDisplay";

export interface BackgroundJobItem {
    jobId: string;
    title: string;
    folderId: string | null;
    /** 합성 중 앞 구간을 미리 듣기 위해 받아 둔 것. 눌렀을 때 받기 시작한다 —
     *  백그라운드로 도는 문서는 스캔본처럼 길어서, 들을지 모르는 오디오를
     *  미리 통째로 내려받으면 안 된다. */
    playableAudio?: Blob;
    playableSentences?: ReaderSentence[];
    /** 눌러서 받는 중. 버튼을 두 번 눌러 두 벌 받지 않게 한다. */
    isPreparingPreview?: boolean;
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
