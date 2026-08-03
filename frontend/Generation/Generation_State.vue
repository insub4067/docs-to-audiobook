<script lang="ts">
import { ref, type Ref } from "vue";

export interface GeneratingItem {
    id: string;
    title: string;
    progressPercent: number;
    statusText: string;
    backgroundJobId?: string;
}

export type AddSourceMode = "menu" | "url" | "paste" | null;

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
    urlInputValue: Ref<string>;
    isUrlFetchBusy: Ref<boolean>;
    pasteTextValue: Ref<string>;
    isPasteBusy: Ref<boolean>;
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
        urlInputValue: ref(""),
        isUrlFetchBusy: ref(false),
        pasteTextValue: ref(""),
        isPasteBusy: ref(false),
        addSourceMode: ref(null),
        speed: ref(5),
        pitch: ref(0),
        generatingItems: ref([]),
        targetFolderId: ref(null),
    };
}

export default {};
</script>
