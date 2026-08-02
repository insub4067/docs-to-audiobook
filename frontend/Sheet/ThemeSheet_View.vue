<script setup lang="ts">
import { ref, watch } from "vue";
import type { ThemeState } from "../Theme/Theme_State.vue";
import type { ThemeLogic } from "../Theme/Theme_Logic.vue";
import { APP_THEME_OPTIONS } from "../Theme/Theme_State.vue";
import { useSwipeToDismiss } from "../utils/swipeToDismiss";

const props = defineProps<{
    state: ThemeState;
    logic: ThemeLogic;
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
        aria-label="화면 테마"
        @click="onBackdropClick"
    >
        <div class="action-sheet" ref="sheet">
            <div class="action-sheet-handle"></div>
            <div class="index-sheet-header">
                <h3>화면 테마</h3>
            </div>
            <div class="theme-preview">
                <p class="theme-preview-heading">1장</p>
                <p class="theme-preview-text">낯선 문장이 익숙한 목소리로 다가올 때, 우리는 비로소 이야기 속에 있다.</p>
            </div>
            <div class="reader-theme-grid">
                <button
                    v-for="option in APP_THEME_OPTIONS"
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
