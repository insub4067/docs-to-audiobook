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

watch(() => props.state.addSourceMode.value, (mode) => {
    document.body.style.overflow = mode ? "hidden" : "";
});

function onBackdropClick(event: MouseEvent): void {
    if (event.target === event.currentTarget) props.logic.closeAddSourceSheet();
}

function onAttachClick(): void {
    props.logic.closeAddSourceSheet();
    props.onSelectFile();
}

function onComposerKeydown(event: KeyboardEvent): void {
    if (event.key === "Enter") {
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
        <div class="add-source-composer" ref="composer">
            <button
                type="button"
                class="composer-attach-btn"
                aria-label="파일 업로드"
                title="파일 업로드 (MD, PDF, TXT, DOCX, HWP)"
                @click="onAttachClick"
            >
                <i data-lucide="plus"></i>
            </button>
            <input
                type="text"
                inputmode="url"
                placeholder="링크를 붙여넣거나 텍스트를 입력하세요"
                v-model="state.composerInputValue.value"
                @keydown="onComposerKeydown"
            >
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
</template>
