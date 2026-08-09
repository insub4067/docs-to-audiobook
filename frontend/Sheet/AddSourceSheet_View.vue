<script setup lang="ts">
import { ref, watch } from "vue";
import type { GenerationState } from "../Generation/Generation_State.vue";
import type { GenerationLogic } from "../Generation/Generation_Logic.vue";
import { useSwipeToDismiss } from "../utils/swipeToDismiss";
import { useAuthStore } from "../stores/auth";
import { usePromptSheetLogic } from "./PromptSheet_Logic.vue";
import { usePromptSheetState } from "./PromptSheet_State.vue";

const props = defineProps<{
    state: GenerationState;
    logic: GenerationLogic;
    onSelectFile: () => void;
    onSelectHighQualityPdf: () => void;
}>();

const authStore = useAuthStore();
const promptSheetLogic = usePromptSheetLogic(usePromptSheetState());

// Generation_Logic.vue의 getUploadLimitBytes()와 같은 값 — 안내 문구용으로만
// 쓰므로 별도 API 호출 없이 그대로 미러링한다. 관리자는 사실상 여유로워
// 굳이 상한을 강조해 보여줄 필요가 없다(글자 수 배지와 같은 판단).
const maxUploadLabel = authStore.isAdmin ? null : "최대 10MB";

const sheet = ref<HTMLElement | null>(null);
useSwipeToDismiss(sheet, () => props.logic.closeAddSourceSheet());

watch(() => props.state.isFileSourceMenuOpen.value, (open) => {
    document.body.style.overflow = open ? "hidden" : "";
});

function onBackdropClick(event: MouseEvent): void {
    if (event.target === event.currentTarget) props.logic.closeAddSourceSheet();
}

function onUploadFileClick(): void {
    props.logic.closeAddSourceSheet();
    props.onSelectFile();
}

function onDriveImportClick(): void {
    props.logic.importFromGoogleDrive();
}

function onTextInputClick(): void {
    props.logic.openTextInputSheet();
}

async function onLinkInputClick(): Promise<void> {
    props.logic.closeAddSourceSheet();
    const raw = await promptSheetLogic.showPrompt("링크를 붙여넣어 주세요", { subtitle: "예: https://example.com/article" });
    if (raw) props.logic.submitPastedLink(raw);
}

function onScanTextClick(): void {
    props.logic.openScanSheet();
}

function onHighQualityPdfClick(): void {
    props.logic.closeAddSourceSheet();
    props.onSelectHighQualityPdf();
}

</script>

<template>
    <div
        class="action-sheet-backdrop"
        :class="{ show: state.isFileSourceMenuOpen.value }"
        role="dialog"
        aria-modal="true"
        aria-label="문서 추가"
        @click="onBackdropClick"
    >
        <div class="action-sheet" ref="sheet">
            <div class="action-sheet-handle"></div>
            <div class="index-sheet-header">
                <h3>문서 추가</h3>
                <p class="action-sheet-subtitle">오디오북으로 만들 문서를 선택하세요</p>
            </div>
            <p class="action-sheet-hint">
                지원 형식: MD · PDF · TXT · DOCX · HWP
                <template v-if="maxUploadLabel"> · {{ maxUploadLabel }}</template>
            </p>

            <button class="action-sheet-btn action-sheet-btn-detailed" type="button" @click="onUploadFileClick">
                <i data-lucide="file-up"></i>
                <span class="action-sheet-btn-text">
                    <span class="action-sheet-btn-title">파일 업로드</span>
                    <span class="action-sheet-btn-desc">기기에 저장된 문서를 선택합니다</span>
                </span>
            </button>
            <button class="action-sheet-btn action-sheet-btn-detailed" type="button" @click="onTextInputClick">
                <i data-lucide="type"></i>
                <span class="action-sheet-btn-text">
                    <span class="action-sheet-btn-title">텍스트 입력</span>
                    <span class="action-sheet-btn-desc">내용을 직접 입력하거나 붙여 넣습니다</span>
                </span>
            </button>
            <button class="action-sheet-btn action-sheet-btn-detailed" type="button" @click="onLinkInputClick">
                <i data-lucide="link"></i>
                <span class="action-sheet-btn-text">
                    <span class="action-sheet-btn-title">링크 입력</span>
                    <span class="action-sheet-btn-desc">웹페이지의 본문을 가져옵니다</span>
                </span>
            </button>
            <button class="action-sheet-btn action-sheet-btn-detailed" type="button" @click="onDriveImportClick">
                <i data-lucide="hard-drive"></i>
                <span class="action-sheet-btn-text">
                    <span class="action-sheet-btn-title">Google Drive에서 가져오기</span>
                    <span class="action-sheet-btn-desc">Drive에 저장된 문서를 선택합니다</span>
                </span>
            </button>

            <template v-if="authStore.isAdmin">
                <div class="action-sheet-divider"></div>
                <p class="action-sheet-section-label">개발자 전용</p>
                <button class="action-sheet-btn action-sheet-btn-detailed" type="button" @click="onScanTextClick">
                    <i data-lucide="scan-text"></i>
                    <span class="action-sheet-btn-text">
                        <span class="action-sheet-btn-title">텍스트 스캔</span>
                        <span class="action-sheet-btn-desc">이미지나 스캔 문서에서 텍스트를 추출합니다</span>
                    </span>
                </button>
                <button class="action-sheet-btn action-sheet-btn-detailed" type="button" @click="onHighQualityPdfClick">
                    <i data-lucide="file-search"></i>
                    <span class="action-sheet-btn-text">
                        <span class="action-sheet-btn-title">고성능 PDF</span>
                        <span class="action-sheet-btn-desc">일반 방식으로 읽지 못한 PDF를 처리합니다</span>
                    </span>
                </button>
            </template>

            <button class="action-sheet-btn action-sheet-btn-cancel" type="button" @click="logic.closeAddSourceSheet">닫기</button>
        </div>
    </div>
</template>
