<script setup lang="ts">
import type { ReaderControlsState } from "./ReaderControls_State.vue";
import type { ReaderControlsLogic } from "./ReaderControls_Logic.vue";

defineProps<{
    state: ReaderControlsState;
    logic: ReaderControlsLogic;
}>();
</script>

<template>
    <div class="reader-secondary-controls">
        <button
            class="btn-reader-secondary"
            :class="{ active: state.repeatMode.value !== 'off' }"
            aria-label="반복 모드"
            type="button"
            @click="logic.openSheet('repeat')"
        >
            <i data-lucide="repeat"></i>
        </button>
        <button
            class="btn-reader-secondary"
            :class="{ active: state.playbackSpeed.value !== 1.0 }"
            aria-label="재생 속도"
            type="button"
            @click="logic.openSheet('speed')"
        >
            <i data-lucide="gauge"></i>
        </button>
        <button
            class="btn-reader-secondary"
            :class="{ active: state.isTimerActive.value }"
            aria-label="취침 타이머"
            type="button"
            @click="logic.openSheet('timer')"
        >
            <i data-lucide="moon"></i>
        </button>
    </div>
</template>
