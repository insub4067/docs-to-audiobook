<script setup lang="ts">
import type { ReaderControlsState } from "./ReaderControls_State.vue";
import type { ReaderControlsLogic } from "./ReaderControls_Logic.vue";

const props = defineProps<{
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
            title="반복 모드"
            type="button"
            @click="logic.openSheet('repeat')"
        >
            <i data-lucide="repeat"></i>
        </button>
        <button
            class="btn-reader-secondary"
            :class="{ active: state.playbackSpeed.value !== 1.0 }"
            aria-label="재생 속도"
            title="재생 속도"
            type="button"
            @click="logic.openSheet('speed')"
        >
            <i data-lucide="gauge"></i>
        </button>
        <button
            class="btn-reader-secondary"
            :class="{ active: state.isTimerActive.value }"
            aria-label="취침 타이머"
            title="취침 타이머"
            type="button"
            @click="logic.openSheet('timer')"
        >
            <i data-lucide="moon"></i>
        </button>
        <button
            class="btn-reader-secondary"
            :class="{ active: state.fontFamily.value !== 'serif' }"
            aria-label="글꼴"
            title="글꼴"
            type="button"
            @click="logic.openSheet('fontFamily')"
        >
            <i data-lucide="type"></i>
        </button>
        <button
            class="btn-reader-secondary"
            :class="{ active: state.fontSize.value !== 1.0 }"
            aria-label="글자 크기"
            title="글자 크기"
            type="button"
            @click="logic.openSheet('fontSize')"
        >
            <i data-lucide="case-sensitive"></i>
        </button>
    </div>
</template>
