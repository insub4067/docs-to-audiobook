<script lang="ts">
import { ref, type Ref } from "vue";

export interface GeneratingItem {
    id: string;
    title: string;
    progressPercent: number;
    statusText: string;
    backgroundJobId?: string;
}

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
    speed: Ref<number>;
    pitch: Ref<number>;
    generatingItems: Ref<GeneratingItem[]>;
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
        speed: ref(5),
        pitch: ref(0),
        generatingItems: ref([]),
    };
}

export default {};
</script>
