<script setup lang="ts">
import type { ReaderState } from "../../Reader/Reader_State.vue";
import type { ReaderLogic } from "../../Reader/Reader_Logic.vue";
import { getAudiobookDisplayTitle } from "../../utils/format";

const props = defineProps<{
    state: ReaderState;
    logic: ReaderLogic;
}>();

function onPlayPauseClick(event: MouseEvent): void {
    event.stopPropagation();
    props.logic.togglePlayPause();
}

function onProgressBarClick(event: MouseEvent): void {
    event.stopPropagation();
    const bar = event.currentTarget as HTMLElement;
    const rect = bar.getBoundingClientRect();
    if (rect.width > 0) props.logic.seekTo((event.clientX - rect.left) / rect.width);
}
</script>

<template>
    <button
        type="button"
        class="mini-player"
        :class="{ show: !state.isOpen.value && !!state.title.value }"
        aria-label="재생 화면 열기"
        @click="logic.reopenReader"
    >
        <div class="mini-player-row">
            <span class="mini-player-title">{{ getAudiobookDisplayTitle(state.title.value) }}</span>
            <button class="mini-player-play-btn" type="button" aria-label="재생 또는 일시정지" @click="onPlayPauseClick">
                <svg v-show="!state.isPlaying.value" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="currentColor" stroke="none"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
                <svg v-show="state.isPlaying.value" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="currentColor" stroke="none"><rect x="6" y="4" width="4" height="16"></rect><rect x="14" y="4" width="4" height="16"></rect></svg>
            </button>
        </div>
        <div class="mini-player-row">
            <span class="mini-player-time">{{ state.currentTimeLabel.value }}</span>
            <div class="mini-player-progress-bar" @click="onProgressBarClick">
                <div class="mini-player-progress-fill" :style="{ width: state.progressPercent.value + '%' }"></div>
            </div>
            <span class="mini-player-time">{{ state.durationLabel.value }}</span>
        </div>
    </button>
</template>
