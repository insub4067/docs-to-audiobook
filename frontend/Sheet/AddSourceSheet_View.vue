<script setup lang="ts">
import { ref, watch } from "vue";
import type { GenerationState } from "../Generation/Generation_State.vue";
import type { GenerationLogic } from "../Generation/Generation_Logic.vue";
import { useSwipeToDismiss } from "../utils/swipeToDismiss";
import { useAuthStore } from "../stores/auth";

const props = defineProps<{
    state: GenerationState;
    logic: GenerationLogic;
    onSelectFile: () => void;
    onSelectHighQualityPdf: () => void;
}>();

const authStore = useAuthStore();

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
    props.logic.closeAddSourceSheet();
    const raw = window.prompt("오디오북으로 만들 텍스트를 붙여넣어 주세요:");
    if (raw) props.logic.submitPastedText(raw);
}

function onLinkInputClick(): void {
    props.logic.closeAddSourceSheet();
    const raw = window.prompt("링크를 붙여넣어 주세요:\n(예: https://example.com/article)");
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
            <p class="action-sheet-hint">지원 형식: MD · PDF · TXT · DOCX · HWP</p>
            <button class="action-sheet-btn" type="button" @click="onUploadFileClick">
                <i data-lucide="file-up"></i>
                파일 업로드
            </button>
            <button class="action-sheet-btn" type="button" @click="onTextInputClick">
                <i data-lucide="type"></i>
                텍스트 입력
            </button>
            <button class="action-sheet-btn" type="button" @click="onLinkInputClick">
                <i data-lucide="link"></i>
                링크 입력
            </button>
            <button class="action-sheet-btn" type="button" @click="onDriveImportClick">
                <i data-lucide="hard-drive"></i>
                Google Drive에서 가져오기
            </button>
            <button v-if="authStore.isAdmin" class="action-sheet-btn" type="button" @click="onScanTextClick">
                <i data-lucide="scan-text"></i>
                텍스트 스캔 (관리자 전용)
            </button>
            <button v-if="authStore.isAdmin" class="action-sheet-btn" type="button" @click="onHighQualityPdfClick">
                <i data-lucide="file-search"></i>
                고성능 PDF (관리자 전용)
            </button>
            <button class="action-sheet-btn action-sheet-btn-cancel" type="button" @click="logic.closeAddSourceSheet">닫기</button>
        </div>
    </div>
</template>
