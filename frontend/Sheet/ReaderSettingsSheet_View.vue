<script setup lang="ts">
import { ref, watch } from "vue";
import type { ReaderState } from "../Reader/Reader_State.vue";
import type { ReaderLogic } from "../Reader/Reader_Logic.vue";
import type { ReaderControlsLogic } from "../Reader/ReaderControls/ReaderControls_Logic.vue";
import type { ThemeLogic } from "../Theme/Theme_Logic.vue";
import { useSwipeToDismiss } from "../utils/swipeToDismiss";

const props = defineProps<{
    state: ReaderState;
    logic: ReaderLogic;
    controlsLogic: ReaderControlsLogic;
    themeLogic: ThemeLogic;
}>();

const sheet = ref<HTMLElement | null>(null);
useSwipeToDismiss(sheet, () => props.logic.closeSettingsSheet());

watch(() => props.state.isSettingsSheetOpen.value, (open) => {
    document.body.style.overflow = open ? "hidden" : "";
});

function onBackdropClick(event: MouseEvent): void {
    if (event.target === event.currentTarget) props.logic.closeSettingsSheet();
}

function onThemeClick(): void {
    props.logic.closeSettingsSheet();
    props.themeLogic.openSheet();
}

function onFontFamilyClick(): void {
    props.logic.closeSettingsSheet();
    props.controlsLogic.openSheet("fontFamily");
}

function onFontSizeClick(): void {
    props.logic.closeSettingsSheet();
    props.controlsLogic.openSheet("fontSize");
}

function onLineHeightClick(): void {
    props.logic.closeSettingsSheet();
    props.controlsLogic.openSheet("lineHeight");
}
</script>

<template>
    <div
        class="action-sheet-backdrop"
        :class="{ show: state.isSettingsSheetOpen.value }"
        role="dialog"
        aria-modal="true"
        aria-label="읽기 설정"
        @click="onBackdropClick"
    >
        <div class="action-sheet" ref="sheet">
            <div class="action-sheet-handle"></div>
            <div class="index-sheet-header">
                <h3>읽기 설정</h3>
            </div>
            <button class="action-sheet-btn" type="button" @click="onThemeClick">
                <i data-lucide="palette"></i>
                읽기 화면 테마
            </button>
            <button class="action-sheet-btn" type="button" @click="onFontFamilyClick">
                <i data-lucide="type"></i>
                글꼴
            </button>
            <button class="action-sheet-btn" type="button" @click="onFontSizeClick">
                <i data-lucide="case-sensitive"></i>
                글자 크기
            </button>
            <button class="action-sheet-btn" type="button" @click="onLineHeightClick">
                <i data-lucide="rows-3"></i>
                줄 간격
            </button>
            <button class="action-sheet-btn action-sheet-btn-cancel" type="button" @click="logic.closeSettingsSheet">닫기</button>
        </div>
    </div>
</template>
