<script lang="ts">
import { ref, type Ref } from "vue";

export interface GeneratingItem {
    id: string;
    title: string;
    progressPercent: number;
    statusText: string;
    backgroundJobId?: string;
    // 내 파일의 어느 폴더에서 추가했는지 — MyFilesView가 지금 보고 있는
    // 폴더에만 진행 중 행을 보여줄 때 쓴다. 홈 화면 드롭존에서 추가한
    // 경우는 null(루트).
    folderId: string | null;
}

export type AddSourceMode = "menu" | null;

export interface GenerationState {
    currentTextId: Ref<string | null>;
    currentTextAccessToken: Ref<string | null>;
    uploadedFileName: Ref<string | null>;
    fileSizeLabel: Ref<string>;
    isFileDetailsVisible: Ref<boolean>;
    isDropzoneLoading: Ref<boolean>;
    isDragOver: Ref<boolean>;
    previewText: Ref<string>;
    isPreviewVisible: Ref<boolean>;
    charCount: Ref<number>;
    isCharBadgeVisible: Ref<boolean>;
    isGenerateDisabled: Ref<boolean>;
    isModalOpen: Ref<boolean>;
    isLoginPromptOpen: Ref<boolean>;
    // 문서 추가 시트의 통합 입력창(링크 붙여넣기/텍스트 붙여넣기 겸용) —
    // 무엇을 붙여넣었는지는 Generation_Logic.vue가 판단한다.
    composerInputValue: Ref<string>;
    isComposerBusy: Ref<boolean>;
    addSourceMode: Ref<AddSourceMode>;
    speed: Ref<number>;
    pitch: Ref<number>;
    generatingItems: Ref<GeneratingItem[]>;
    // 내 파일 화면에서 폴더 안에 있는 동안 문서를 추가하면, 생성된
    // 오디오북이 root가 아니라 이 폴더에 들어가야 한다. 홈 화면
    // 드롭존에서 시작한 추가는 항상 null(루트)이어야 한다.
    targetFolderId: Ref<string | null>;
}

export function useGenerationState(): GenerationState {
    return {
        currentTextId: ref(null),
        currentTextAccessToken: ref(null),
        uploadedFileName: ref(null),
        fileSizeLabel: ref(""),
        isFileDetailsVisible: ref(false),
        isDropzoneLoading: ref(false),
        isDragOver: ref(false),
        previewText: ref(""),
        isPreviewVisible: ref(false),
        charCount: ref(0),
        isCharBadgeVisible: ref(false),
        isGenerateDisabled: ref(true),
        isModalOpen: ref(false),
        isLoginPromptOpen: ref(false),
        composerInputValue: ref(""),
        isComposerBusy: ref(false),
        addSourceMode: ref(null),
        speed: ref(5),
        pitch: ref(0),
        generatingItems: ref([]),
        targetFolderId: ref(null),
    };
}

export default {};
</script>
