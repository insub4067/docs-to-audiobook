<script setup lang="ts">
import { computed, ref } from "vue";
import type { ReaderState } from "../../Reader/Reader_State.vue";
import type { ReaderLogic } from "../../Reader/Reader_Logic.vue";
import { getAudiobookDisplayTitle, formatTime } from "../../utils/format";

const props = defineProps<{
    state: ReaderState;
    logic: ReaderLogic;
}>();

function onPlayPauseClick(event: MouseEvent): void {
    event.stopPropagation();
    props.logic.togglePlayPause();
}

// 읽기 화면의 진행 바와 같은 조작 — 끌어서 옮기고, 끄는 동안 어느 시각으로
// 가는지 말풍선으로 보여준다. 놓기 전까지는 실제로 옮기지 않는다.
//
// 미니 플레이어는 전체가 "읽기 화면 열기" 버튼이라, 여기서 일어난 포인터
// 이벤트가 위로 올라가면 끌기만 해도 리더가 열려 버린다. 그래서 전부
// stopPropagation한다.
const dragFraction = ref<number | null>(null);

const dragTimeLabel = computed(() => {
    if (dragFraction.value === null) return "";
    return formatTime(props.state.durationSeconds.value * dragFraction.value);
});

function fractionFromEvent(bar: HTMLElement, clientX: number): number {
    const rect = bar.getBoundingClientRect();
    if (rect.width <= 0) return 0;
    return Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
}

function onProgressPointerDown(event: PointerEvent): void {
    event.stopPropagation();
    const bar = event.currentTarget as HTMLElement;
    bar.setPointerCapture(event.pointerId);
    dragFraction.value = fractionFromEvent(bar, event.clientX);
}

function onProgressPointerMove(event: PointerEvent): void {
    if (dragFraction.value === null) return;
    event.stopPropagation();
    dragFraction.value = fractionFromEvent(event.currentTarget as HTMLElement, event.clientX);
}

function onProgressPointerUp(event: PointerEvent): void {
    if (dragFraction.value === null) return;
    event.stopPropagation();
    const fraction = fractionFromEvent(event.currentTarget as HTMLElement, event.clientX);
    dragFraction.value = null;
    props.logic.seekTo(fraction);
}

function onProgressPointerCancel(): void {
    dragFraction.value = null;
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
            <div
                class="mini-player-progress-bar"
                :class="{ 'is-dragging': dragFraction !== null }"
                @click.stop
                @pointerdown="onProgressPointerDown"
                @pointermove="onProgressPointerMove"
                @pointerup="onProgressPointerUp"
                @pointercancel="onProgressPointerCancel"
            >
                <div
                    class="mini-player-progress-fill"
                    :style="{ width: (dragFraction !== null ? dragFraction * 100 : state.progressPercent.value) + '%' }"
                ></div>
                <span
                    v-if="dragFraction !== null"
                    class="player-progress-tooltip"
                    :style="{ left: dragFraction * 100 + '%' }"
                >{{ dragTimeLabel }}</span>
            </div>
            <span class="mini-player-time">{{ state.durationLabel.value }}</span>
        </div>
    </button>
</template>
