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
    isComposerBusy: Ref<boolean>;
    // 파일 업로드/구글 드라이브/텍스트 입력/링크 입력 등 문서 소스를
    // 고르는 시트("문서 추가").
    isFileSourceMenuOpen: Ref<boolean>;
    // 텍스트 스캔(OCR, 관리자 전용) — 여러 장을 연속 촬영해서 모아뒀다가
    // 한 번에 추출한다. 아직 서버로 보내지 않은 대기열.
    isScanSheetOpen: Ref<boolean>;
    scannedImages: Ref<File[]>;
    // "텍스트 입력" — window.prompt는 한 줄짜리라 긴 글 붙여넣기에 안 맞아
    // 큰 textarea가 있는 전용 시트를 쓴다.
    isTextInputSheetOpen: Ref<boolean>;
    textInputValue: Ref<string>;
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
        isComposerBusy: ref(false),
        isFileSourceMenuOpen: ref(false),
        isScanSheetOpen: ref(false),
        scannedImages: ref([]),
        isTextInputSheetOpen: ref(false),
        textInputValue: ref(""),
        speed: ref(5),
        pitch: ref(0),
        generatingItems: ref([]),
        targetFolderId: ref(null),
    };
}

export default {};
</script>
