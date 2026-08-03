<script setup lang="ts">
import { ref, watch } from "vue";
import type { GenerationState } from "../Generation/Generation_State.vue";
import type { GenerationLogic } from "../Generation/Generation_Logic.vue";
import { useSwipeToDismiss } from "../utils/swipeToDismiss";

const props = defineProps<{
    state: GenerationState;
    logic: GenerationLogic;
    onSelectFile: () => void;
}>();

const composer = ref<HTMLElement | null>(null);
useSwipeToDismiss(composer, () => props.logic.closeAddSourceSheet());

const fileSourceSheet = ref<HTMLElement | null>(null);
useSwipeToDismiss(fileSourceSheet, () => props.logic.closeFileSourceMenu());

const composerPlaceholder = "링크를 붙여넣거나\n텍스트를 입력하세요";

// 진입 애니메이션이 끝나야만 transform을 완전히 없앤다(스타일 쪽 설명
// 참고) — iOS에서 입력창에 포커스를 줬을 때 커서가 화면 하단에 엉뚱하게
// 그려지는 버그를 피하기 위함이다.
const isSettled = ref(false);
function onComposerTransitionEnd(event: TransitionEvent): void {
    if (event.propertyName === "transform" && event.target === composer.value) {
        isSettled.value = !!props.state.addSourceMode.value;
    }
}

watch(() => props.state.addSourceMode.value, (mode) => {
    document.body.style.overflow = mode ? "hidden" : "";
    if (!mode) isSettled.value = false;
});

function onBackdropClick(event: MouseEvent): void {
    if (event.target === event.currentTarget) props.logic.closeAddSourceSheet();
}

function onFileSourceBackdropClick(event: MouseEvent): void {
    if (event.target === event.currentTarget) props.logic.closeFileSourceMenu();
}

function onUploadFileClick(): void {
    props.logic.closeFileSourceMenu();
    props.logic.closeAddSourceSheet();
    props.onSelectFile();
}

function onDriveImportClick(): void {
    props.logic.importFromGoogleDrive();
}

function onComposerKeydown(event: KeyboardEvent): void {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        props.logic.submitComposerInput();
    }
}
</script>

<template>
    <div
        class="action-sheet-backdrop composer-backdrop"
        :class="{ show: !!state.addSourceMode.value }"
        role="dialog"
        aria-modal="true"
        aria-label="문서 추가"
        @click="onBackdropClick"
    >
        <div
            class="add-source-composer"
            :class="{ settled: isSettled }"
            ref="composer"
            @transitionend="onComposerTransitionEnd"
        >
            <button
                type="button"
                class="composer-attach-btn"
                aria-label="파일 소스 선택"
                title="파일 업로드 또는 Google Drive에서 가져오기"
                @click="logic.openFileSourceMenu"
            >
                <i data-lucide="plus"></i>
            </button>
            <textarea
                rows="2"
                :placeholder="composerPlaceholder"
                v-model="state.composerInputValue.value"
                @keydown="onComposerKeydown"
            ></textarea>
            <button
                type="button"
                class="composer-submit-btn"
                :class="{ 'is-loading': state.isComposerBusy.value }"
                :disabled="state.isComposerBusy.value || !state.composerInputValue.value.trim()"
                aria-label="추가"
                title="추가"
                @click="logic.submitComposerInput"
            >
                <i data-lucide="arrow-up"></i>
            </button>
        </div>
    </div>

    <div
        class="action-sheet-backdrop"
        :class="{ show: state.isFileSourceMenuOpen.value }"
        role="dialog"
        aria-modal="true"
        aria-label="파일 소스 선택"
        @click="onFileSourceBackdropClick"
    >
        <div class="action-sheet" ref="fileSourceSheet">
            <div class="action-sheet-handle"></div>
            <button class="action-sheet-btn" type="button" @click="onUploadFileClick">
                <i data-lucide="file-up"></i>
                파일 업로드 (MD, PDF, TXT, DOCX, HWP)
            </button>
            <button class="action-sheet-btn" type="button" @click="onDriveImportClick">
                <i data-lucide="hard-drive"></i>
                Google Drive에서 가져오기
            </button>
            <button class="action-sheet-btn action-sheet-btn-cancel" type="button" @click="logic.closeFileSourceMenu">닫기</button>
        </div>
    </div>
</template>
