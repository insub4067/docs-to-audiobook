<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
import type { GenerationState } from "../Generation/Generation_State.vue";
import type { GenerationLogic } from "../Generation/Generation_Logic.vue";
import { useSwipeToDismiss } from "../utils/swipeToDismiss";

const props = defineProps<{
    state: GenerationState;
    logic: GenerationLogic;
}>();

const sheet = ref<HTMLElement | null>(null);
useSwipeToDismiss(sheet, () => props.logic.closeTextInputSheet());

const textarea = ref<HTMLTextAreaElement | null>(null);

// window.prompt는 한 줄짜리인 데다 iOS PWA에서 자동 포커스도 안 돼서,
// 시트가 열리자마자 큰 textarea에 바로 커서가 가도록 한다.
watch(() => props.state.isTextInputSheetOpen.value, (open) => {
    document.body.style.overflow = open ? "hidden" : "";
    if (open) nextTick(() => textarea.value?.focus());
});

function onBackdropClick(event: MouseEvent): void {
    if (event.target === event.currentTarget) props.logic.closeTextInputSheet();
}
</script>

<template>
    <div
        class="action-sheet-backdrop"
        :class="{ show: state.isTextInputSheetOpen.value }"
        role="dialog"
        aria-modal="true"
        aria-label="텍스트 입력"
        @click="onBackdropClick"
    >
        <div class="action-sheet text-input-sheet" ref="sheet">
            <div class="action-sheet-handle"></div>
            <div class="index-sheet-header">
                <h3>텍스트 입력</h3>
            </div>
            <textarea
                ref="textarea"
                class="text-input-textarea"
                placeholder="오디오북으로 만들 텍스트를 붙여넣거나 입력하세요"
                v-model="state.textInputValue.value"
            ></textarea>
            <button
                class="action-sheet-btn action-sheet-btn-primary"
                type="button"
                :disabled="!state.textInputValue.value.trim() || state.isComposerBusy.value"
                @click="logic.submitTextInputSheet"
            >
                <i data-lucide="arrow-up-circle"></i>
                {{ state.isComposerBusy.value ? "추출 중..." : "추가하기" }}
            </button>
            <button class="action-sheet-btn action-sheet-btn-cancel" type="button" @click="logic.closeTextInputSheet">닫기</button>
        </div>
    </div>
</template>
