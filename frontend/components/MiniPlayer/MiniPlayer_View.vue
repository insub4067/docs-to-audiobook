<script setup lang="ts">
import { computed, ref } from "vue";
import type { ReaderState } from "../../Reader/Reader_State.vue";
import type { ReaderLogic } from "../../Reader/Reader_Logic.vue";
import type { AudioListState } from "../Library/AudioList_State.vue";
import { getAudiobookDisplayTitle, formatTime } from "../../utils/format";
import { usePlaylistNavigation } from "./playlistNavigation";
import { useToastLogic } from "../Toast/Toast_Logic.vue";
import { useToastState } from "../Toast/Toast_State.vue";

const props = defineProps<{
    state: ReaderState;
    logic: ReaderLogic;
    audioListState: AudioListState;
}>();

const { showToast } = useToastLogic(useToastState());
const playlist = usePlaylistNavigation(props.state, props.audioListState, props.logic);

function onPlayPauseClick(event: MouseEvent): void {
    event.stopPropagation();
    props.logic.togglePlayPause();
}

// ── 진행 바 ────────────────────────────────────────────────────────────
// 읽기 화면의 진행 바와 같은 조작 — 끌어서 옮기고, 끄는 동안 어느 시각으로
// 가는지 말풍선으로 보여준다. 놓기 전까지는 실제로 옮기지 않는다.
//
// 미니 플레이어는 전체가 "읽기 화면 열기" 버튼이고 스와이프 제스처도
// 받는다. 진행 바에서 일어난 포인터 이벤트가 위로 올라가면 끌기만 해도
// 리더가 열리거나 재생목록이 넘어가므로 전부 stopPropagation한다.
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

// ── 스와이프 제스처 ────────────────────────────────────────────────────
// 아래로 쓸어내리면 내려가고, 좌우로 쓸면 재생목록을 앞뒤로 옮긴다.
// 왼쪽으로 미는 건 "다음 것을 당겨온다"는 뜻이라 다음 항목이다.
const SWIPE_THRESHOLD = 60;
// 방향을 정하기 전에 조금 움직여 봐야 한다 — 처음 몇 px로 축을 정하면
// 손가락이 살짝 흔들린 것만으로 엉뚱한 축에 갇힌다.
const AXIS_LOCK_DISTANCE = 8;

const swipeOffset = ref<{ x: number; y: number } | null>(null);
let swipeStartX = 0;
let swipeStartY = 0;
let swipeAxis: "none" | "x" | "y" = "none";
// 스와이프로 끝난 제스처의 click까지 리더를 여는 걸 막는다.
let swipeHandled = false;

// 유튜브 뮤직처럼 바는 제자리에 두고 안쪽 제목만 미끄러진다. 진행 바와
// 재생 버튼까지 통째로 밀면 조작 중인 컨트롤이 손가락을 따라 도망간다.
const titleSlideStyle = computed(() => {
    const offset = swipeOffset.value;
    if (!offset || offset.x === 0) return undefined;
    return {
        transform: `translateX(${offset.x}px)`,
        transition: "none",
        opacity: String(Math.max(0.2, 1 - Math.abs(offset.x) / 220)),
    };
});

// 아래로 내리는 건 바 전체가 내려가는 게 맞다.
const dismissStyle = computed(() => {
    const offset = swipeOffset.value;
    if (!offset || offset.y === 0) return undefined;
    return {
        transform: `translateY(${offset.y}px)`,
        transition: "none",
        opacity: String(Math.max(0.3, 1 - offset.y / 160)),
    };
});

// 다음/이전 중 어느 쪽으로 넘겼는지에 따라 새 제목이 들어오는 방향이 달라진다.
const slideDirection = ref<"next" | "prev">("next");

function onRootPointerDown(event: PointerEvent): void {
    // 포인터를 붙잡아 둬야 손가락이 미니 플레이어 밖으로 나가도 move/up이
    // 계속 온다. 진행 바 드래그가 되고 스와이프가 안 되던 차이가 이것이었다.
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
    swipeStartX = event.clientX;
    swipeStartY = event.clientY;
    swipeAxis = "none";
    swipeHandled = false;
    swipeOffset.value = { x: 0, y: 0 };
}

function onRootPointerMove(event: PointerEvent): void {
    if (!swipeOffset.value) return;
    const deltaX = event.clientX - swipeStartX;
    const deltaY = event.clientY - swipeStartY;

    if (swipeAxis === "none") {
        if (Math.abs(deltaX) < AXIS_LOCK_DISTANCE && Math.abs(deltaY) < AXIS_LOCK_DISTANCE) return;
        swipeAxis = Math.abs(deltaX) > Math.abs(deltaY) ? "x" : "y";
    }
    // 위로는 따라가지 않는다 — 올릴 곳이 없다.
    if (swipeAxis === "y" && deltaY < 0) return;
    swipeOffset.value = swipeAxis === "x" ? { x: deltaX, y: 0 } : { x: 0, y: deltaY };
}

function onRootPointerUp(): void {
    const offset = swipeOffset.value;
    swipeOffset.value = null;
    if (!offset || swipeAxis === "none") return;

    swipeHandled = true;
    if (swipeAxis === "y" && offset.y > SWIPE_THRESHOLD) {
        props.logic.dismissMiniPlayer();
        return;
    }
    if (swipeAxis === "x" && Math.abs(offset.x) > SWIPE_THRESHOLD) {
        const movedToNext = offset.x < 0;
        slideDirection.value = movedToNext ? "next" : "prev";
        // 읽기 화면은 펼치지 않는다 — 미니 플레이어에서 넘기는 것뿐이다.
        if (!playlist.goToOffset(movedToNext ? 1 : -1, { openReaderUI: false })) {
            showToast(movedToNext ? "마지막 항목이에요" : "첫 항목이에요", "info");
        }
    }
}

function onRootPointerCancel(): void {
    swipeOffset.value = null;
}

function onRootClick(): void {
    if (swipeHandled) {
        swipeHandled = false;
        return;
    }
    props.logic.reopenReader();
}
</script>

<template>
    <button
        type="button"
        class="mini-player"
        :class="{ show: !state.isOpen.value && !!state.title.value }"
        :style="dismissStyle"
        aria-label="재생 화면 열기"
        @click="onRootClick"
        @pointerdown="onRootPointerDown"
        @pointermove="onRootPointerMove"
        @pointerup="onRootPointerUp"
        @pointercancel="onRootPointerCancel"
    >
        <div class="mini-player-row">
            <div class="mini-player-title-slot">
                <Transition :name="`mini-title-${slideDirection}`" mode="out-in">
                    <span
                        class="mini-player-title"
                        :key="state.title.value"
                        :style="titleSlideStyle"
                    >{{ getAudiobookDisplayTitle(state.title.value) }}</span>
                </Transition>
            </div>
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
