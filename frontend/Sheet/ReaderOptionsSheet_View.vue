<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { ReaderControlsState } from "../Reader/ReaderControls/ReaderControls_State.vue";
import type { ReaderControlsLogic } from "../Reader/ReaderControls/ReaderControls_Logic.vue";
import { REPEAT_MODES, REPEAT_LABELS, SPEED_OPTIONS, TIMER_OPTIONS_MIN, TIMER_LABELS } from "../Reader/ReaderControls/ReaderControls_Logic.vue";
import { useSwipeToDismiss } from "../utils/swipeToDismiss";

const props = defineProps<{
    state: ReaderControlsState;
    logic: ReaderControlsLogic;
}>();

const sheet = ref<HTMLElement | null>(null);
useSwipeToDismiss(sheet, () => props.logic.closeSheet());

watch(() => props.state.activeSheet.value, (kind) => {
    document.body.style.overflow = kind ? "hidden" : "";
});

const title = computed(() => {
    if (props.state.activeSheet.value === "repeat") return "반복 모드";
    if (props.state.activeSheet.value === "speed") return "재생 속도";
    if (props.state.activeSheet.value === "timer") return "취침 타이머";
    return "";
});

interface OptionRow {
    key: string;
    label: string;
    isSelected: boolean;
    select: () => void;
}

const options = computed<OptionRow[]>(() => {
    const kind = props.state.activeSheet.value;
    if (kind === "repeat") {
        return REPEAT_MODES.map((mode) => ({
            key: mode,
            label: REPEAT_LABELS[mode],
            isSelected: props.state.repeatMode.value === mode,
            select: () => props.logic.selectRepeatMode(mode),
        }));
    }
    if (kind === "speed") {
        return SPEED_OPTIONS.map((value) => ({
            key: String(value),
            label: `${value}x`,
            isSelected: props.state.playbackSpeed.value === value,
            select: () => props.logic.selectSpeed(value),
        }));
    }
    if (kind === "timer") {
        return TIMER_OPTIONS_MIN.map((minutes) => ({
            key: String(minutes),
            label: TIMER_LABELS[minutes],
            isSelected: minutes === 0 ? !props.state.isTimerActive.value : false,
            select: () => props.logic.selectTimerMinutes(minutes),
        }));
    }
    return [];
});

function onBackdropClick(event: MouseEvent): void {
    if (event.target === event.currentTarget) props.logic.closeSheet();
}
</script>

<template>
    <div
        class="action-sheet-backdrop"
        :class="{ show: state.activeSheet.value !== null }"
        role="dialog"
        aria-modal="true"
        :aria-label="title"
        @click="onBackdropClick"
    >
        <div class="action-sheet" ref="sheet">
            <div class="action-sheet-handle"></div>
            <div class="index-sheet-header">
                <h3>{{ title }}</h3>
            </div>
            <button
                v-for="option in options"
                :key="option.key"
                class="action-sheet-btn"
                :class="{ 'is-selected': option.isSelected }"
                @click="option.select"
            >
                <span class="option-check-slot"><i v-if="option.isSelected" data-lucide="check"></i></span>
                {{ option.label }}
            </button>
            <button class="action-sheet-btn action-sheet-btn-cancel" @click="logic.closeSheet">닫기</button>
        </div>
    </div>
</template>
