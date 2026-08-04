<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
import { usePromptSheetState } from "./PromptSheet_State.vue";
import { usePromptSheetLogic } from "./PromptSheet_Logic.vue";
import { useSwipeToDismiss } from "../utils/swipeToDismiss";

const state = usePromptSheetState();
const logic = usePromptSheetLogic(state);

const sheet = ref<HTMLElement | null>(null);
useSwipeToDismiss(sheet, () => logic.cancel());

const inputEl = ref<HTMLInputElement | null>(null);

watch(() => state.isOpen.value, (open) => {
    document.body.style.overflow = open ? "hidden" : "";
    if (open) {
        nextTick(() => {
            inputEl.value?.focus();
            inputEl.value?.select();
        });
    }
});

function onBackdropClick(event: MouseEvent): void {
    if (event.target === event.currentTarget) logic.cancel();
}

function onKeydown(event: KeyboardEvent): void {
    if (event.key === "Enter") logic.confirm();
}
</script>

<template>
    <div
        class="action-sheet-backdrop"
        :class="{ show: state.isOpen.value }"
        role="dialog"
        aria-modal="true"
        :aria-label="state.title.value"
        @click="onBackdropClick"
    >
        <div class="action-sheet" ref="sheet">
            <div class="action-sheet-handle"></div>
            <div class="index-sheet-header">
                <h3>{{ state.title.value }}</h3>
                <p v-if="state.subtitle.value" class="action-sheet-subtitle">{{ state.subtitle.value }}</p>
            </div>
            <input
                ref="inputEl"
                class="prompt-sheet-input"
                :type="state.numeric.value ? 'number' : 'text'"
                :inputmode="state.numeric.value ? 'numeric' : undefined"
                v-model="state.value.value"
                @keydown="onKeydown"
            >
            <button class="action-sheet-btn action-sheet-btn-primary" type="button" @click="logic.confirm">확인</button>
            <button class="action-sheet-btn action-sheet-btn-cancel" type="button" @click="logic.cancel">취소</button>
        </div>
    </div>
</template>
