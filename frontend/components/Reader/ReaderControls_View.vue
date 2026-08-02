<script setup lang="ts">
import type { ReaderControlsState } from "../../composables/Reader/ReaderControls_State.vue";
import type { ReaderControlsLogic } from "../../composables/Reader/ReaderControls_Logic.vue";

const props = defineProps<{
    state: ReaderControlsState;
    logic: ReaderControlsLogic;
}>();

const REPEAT_LABELS: Record<string, string> = { off: "반복 안 함", all: "전체 반복", one: "한 곡 반복" };
</script>

<template>
    <div class="reader-secondary-controls">
        <button
            class="btn-reader-secondary"
            :class="{ active: state.repeatMode.value !== 'off' }"
            aria-label="반복 모드"
            title="반복 모드"
            type="button"
            @click="logic.toggleRepeat"
        >
            <i data-lucide="repeat"></i> <span>{{ REPEAT_LABELS[state.repeatMode.value] }}</span>
        </button>
        <button
            class="btn-reader-secondary"
            :class="{ active: state.playbackSpeed.value !== 1.0 }"
            aria-label="재생 속도"
            title="재생 속도"
            type="button"
            @click="logic.cycleSpeed"
        >
            <i data-lucide="gauge"></i> <span>{{ state.playbackSpeed.value.toFixed(2).replace(/\.00$/, ".0") }}x</span>
        </button>
        <button
            class="btn-reader-secondary"
            :class="{ active: state.isTimerActive.value }"
            aria-label="취침 타이머"
            title="취침 타이머"
            type="button"
            @click="logic.cycleTimer"
        >
            <i data-lucide="moon"></i> <span>{{ state.timerLabel.value }}</span>
        </button>
    </div>
</template>
