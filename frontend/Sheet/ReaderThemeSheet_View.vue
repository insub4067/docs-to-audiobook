<script setup lang="ts">
import { ref, watch } from "vue";
import type { ReaderThemeState } from "../Reader/ReaderTheme_State.vue";
import type { ReaderThemeLogic } from "../Reader/ReaderTheme_Logic.vue";
import { READER_THEME_OPTIONS } from "../Reader/ReaderTheme_State.vue";
import { useSwipeToDismiss } from "../utils/swipeToDismiss";

const props = defineProps<{
    state: ReaderThemeState;
    logic: ReaderThemeLogic;
}>();

const sheet = ref<HTMLElement | null>(null);
useSwipeToDismiss(sheet, () => props.logic.closeSheet());

watch(() => props.state.isSheetOpen.value, (open) => {
    document.body.style.overflow = open ? "hidden" : "";
});

function onBackdropClick(event: MouseEvent): void {
    if (event.target === event.currentTarget) props.logic.closeSheet();
}
</script>

<template>
    <div
        class="action-sheet-backdrop"
        :class="{ show: state.isSheetOpen.value }"
        role="dialog"
        aria-modal="true"
        aria-label="읽기 화면 테마"
        @click="onBackdropClick"
    >
        <div class="action-sheet" ref="sheet">
            <div class="action-sheet-handle"></div>
            <div class="index-sheet-header">
                <h3>읽기 화면</h3>
            </div>
            <div class="reader-theme-grid">
                <button
                    v-for="option in READER_THEME_OPTIONS"
                    :key="option.value"
                    class="reader-theme-card"
                    :class="{ 'is-selected': state.activeTheme.value === option.value }"
                    @click="logic.selectTheme(option.value)"
                >
                    <span class="reader-theme-swatch" :style="{ backgroundColor: option.swatchBg }"></span>
                    <span class="reader-theme-label">{{ option.label }}</span>
                </button>
            </div>
            <button class="action-sheet-btn action-sheet-btn-cancel" @click="logic.closeSheet">닫기</button>
        </div>
    </div>
</template>
