<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, type ComponentPublicInstance } from "vue";
import { formatTime } from "../utils/format";
import type { ReaderState } from "./Reader_State.vue";
import type { ReaderLogic } from "./Reader_Logic.vue";
import type { ReaderControlsState } from "./ReaderControls/ReaderControls_State.vue";
import type { ReaderControlsLogic } from "./ReaderControls/ReaderControls_Logic.vue";
import type { AudioListLogic } from "../components/Library/AudioList_Logic.vue";
import type { AudioListState } from "../components/Library/AudioList_State.vue";
import ReaderControlsView from "./ReaderControls/ReaderControls_View.vue";
import IndexSheetView from "../Sheet/IndexSheet_View.vue";
import ReaderMoreSheetView from "../Sheet/ReaderMoreSheet_View.vue";
import ReaderSettingsSheetView from "../Sheet/ReaderSettingsSheet_View.vue";
import ReaderOptionsSheetView from "../Sheet/ReaderOptionsSheet_View.vue";
import ReaderPlaylistSheetView from "../Sheet/ReaderPlaylistSheet_View.vue";
import BookmarkSheetView from "../Sheet/BookmarkSheet_View.vue";
import type { ThemeLogic } from "../Theme/Theme_Logic.vue";
import { useSwipeToDismiss } from "../utils/swipeToDismiss";

const props = defineProps<{
    state: ReaderState;
    logic: ReaderLogic;
    controlsState: ReaderControlsState;
    controlsLogic: ReaderControlsLogic;
    audioListLogic: AudioListLogic;
    audioListState: AudioListState;
    themeLogic: ThemeLogic;
}>();

// 폴더에 담겨 있거나 경제 뉴스로 열렸을 때만 "같이 묶인 다른 항목"이
// 있을 수 있어, 그때만 제목을 눌러 재생목록을 고를 수 있게 한다.
const hasPlaylist = computed(() =>
    props.state.sharedPlaylistKind.value === "news" || !!props.state.currentAudioObject.value?.folderId
);

// 긴 제목은 한 줄 말줄임이라 화면에서 끝을 알 수 없다. 눌러서 전체를
// 보여준다 — 모바일에는 hover 툴팁이 없어 title 속성만으로는 부족하다.
const isTitleExpanded = ref(false);

function onTitleClick(): void {
    isTitleExpanded.value = !isTitleExpanded.value;
}

function onShareClick(): void {
    const audio = props.state.currentAudioObject.value;
    if (audio) props.audioListLogic.performShare(audio);
}

// 진행 바를 끌어서 이동할 수 있게 한다. 두 시간짜리 경전에서 탭만으로는
// 원하는 지점을 정확히 짚기 어렵다. 끄는 동안에는 어느 시각으로 가는지
// 말풍선으로 보여준다 — 놓기 전까지는 실제로 옮기지 않는다.
const dragFraction = ref<number | null>(null);

function fractionFromEvent(bar: HTMLElement, clientX: number): number {
    const rect = bar.getBoundingClientRect();
    if (rect.width <= 0) return 0;
    return Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
}

const dragTimeLabel = computed(() => {
    if (dragFraction.value === null) return "";
    return formatTime(props.state.durationSeconds.value * dragFraction.value);
});

function onProgressPointerDown(event: PointerEvent): void {
    const bar = event.currentTarget as HTMLElement;
    bar.setPointerCapture(event.pointerId);
    dragFraction.value = fractionFromEvent(bar, event.clientX);
}

function onProgressPointerMove(event: PointerEvent): void {
    if (dragFraction.value === null) return;
    dragFraction.value = fractionFromEvent(event.currentTarget as HTMLElement, event.clientX);
}

function onProgressPointerUp(event: PointerEvent): void {
    if (dragFraction.value === null) return;
    const fraction = fractionFromEvent(event.currentTarget as HTMLElement, event.clientX);
    dragFraction.value = null;
    props.logic.seekTo(fraction);
}

function onProgressPointerCancel(): void {
    dragFraction.value = null;
}

// 인라인 화살표를 :ref에 바로 쓰면 이 컴포넌트가 리렌더될 때마다(재생 중
// activeIndex가 바뀔 때마다) 매번 새 함수로 취급돼 Vue가 null로 껐다가
// 다시 채운다 — measureReaderBars처럼 한 번만 실행되는 rAF 콜백이 그
// 찰나의 null 구간과 겹치면 아무것도 측정하지 못한다. 이름 있는 함수로
// 참조를 고정해 매 렌더마다 재실행되지 않게 한다.
function setContainerEl(el: Element | ComponentPublicInstance | null): void {
    props.state.containerEl.value = el instanceof HTMLElement ? el : null;
}
function setContentEl(el: Element | ComponentPublicInstance | null): void {
    props.state.contentEl.value = el instanceof HTMLElement ? el : null;
}
function setAudioEl(el: Element | ComponentPublicInstance | null): void {
    props.state.audioEl.value = el instanceof HTMLAudioElement ? el : null;
}

let detachResizeHandler: (() => void) | null = null;
onMounted(() => {
    detachResizeHandler = props.logic.attachReaderResizeHandler();
});
onUnmounted(() => detachResizeHandler?.());

// 상단바를 끌어내리면 화면 전체가 따라 내려가다가, 충분히 끌면(또는
// 빠르게 튕기면) 읽기 화면을 닫는다 — 다른 바텀시트들과 같은 제스처를
// 손잡이만 상단바로 바꿔 쓴다.
const header = ref<HTMLElement | null>(null);
useSwipeToDismiss(props.state.containerEl, () => props.logic.closeReader(), header);
</script>

<template>
    <div class="reader-overlay" :class="{ show: state.isOpen.value }" role="dialog" aria-modal="true" aria-label="오디오북 듣기">
        <div class="reader-container" :ref="setContainerEl">
            <header class="reader-header" ref="header">
                <button class="btn-reader-close" aria-label="오디오북 듣기 닫기" type="button" @click="logic.closeReader">
                    <i data-lucide="chevron-left"></i>
                </button>
                <h3
                    class="reader-book-title"
                    :class="{ 'is-expanded': isTitleExpanded }"
                    @click="onTitleClick"
                >{{ state.title.value }}</h3>
                <div class="reader-header-actions">
                    <button
                        v-if="hasPlaylist"
                        type="button"
                        class="btn-reader-close"
                        :class="{ 'is-active': state.isPlaylistSheetOpen.value }"
                        aria-label="재생목록"
                        @click="logic.openPlaylistSheet"
                    >
                        <i data-lucide="list-music"></i>
                    </button>
                    <button class="btn-reader-close" aria-label="더보기" type="button" @click="logic.openMoreSheet">
                        <i data-lucide="more-horizontal"></i>
                    </button>
                </div>
            </header>

            <div
                class="reader-content"
                :ref="setContentEl"
                :style="{
                    fontFamily: controlsState.fontFamily.value === 'sans' ? 'var(--font-sans)' : 'var(--font-serif)',
                    '--reader-font-scale': controlsState.fontSize.value,
                    '--reader-line-height': controlsState.lineHeight.value,
                    // 글꼴이 실제로 차지하는 세로 높이(em). 강조 배경이 줄마다
                    // 끊기지 않게 여백을 계산하는 데 쓴다 — 실측값이라 글꼴을
                    // 바꾸면 같이 바뀌어야 한다(style.css의 .reader-sentence).
                    '--reader-glyph-height': controlsState.fontFamily.value === 'sans' ? '1.46em' : '1.52em',
                }"
                @scroll="logic.onReaderContentScroll"
            >
                <template v-for="(item, itemIdx) in state.displayItems.value" :key="itemIdx">
                    <component v-if="item.kind === 'heading'" :is="'h' + item.level" class="reader-heading" :class="`h${item.level}`">
                        <span
                            :id="`sent-${item.index}`"
                            class="reader-sentence"
                            :class="{ highlight: state.activeIndex.value === item.index }"
                            @click="logic.onSentenceClick(item.index)"
                        >{{ item.text }}</span>
                    </component>
                    <span
                        v-else-if="item.kind === 'sentence'"
                        :id="`sent-${item.index}`"
                        class="reader-sentence"
                        :class="{ highlight: state.activeIndex.value === item.index }"
                        @click="logic.onSentenceClick(item.index)"
                    >{{ item.text }}</span>
                    <table v-else class="reader-table">
                        <thead>
                            <tr>
                                <th v-for="(h, i) in item.header" :key="i">{{ h }}</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr v-for="(row, ri) in item.rows" :key="ri">
                                <td v-for="(cell, ci) in row" :key="ci">
                                    <span
                                        v-if="cell"
                                        :id="`sent-${cell.index}`"
                                        class="reader-sentence"
                                        :class="{ highlight: state.activeIndex.value === cell.index }"
                                        @click="logic.onSentenceClick(cell.index)"
                                    >{{ cell.text }}</span>
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </template>
            </div>

            <button
                v-if="state.isScrolledAway.value"
                type="button"
                class="reader-back-to-current"
                @click="logic.jumpToCurrentSentence"
            >
                <i data-lucide="chevron-up"></i>
                현재 위치로
            </button>

            <footer class="reader-controls">
                <audio :ref="setAudioEl"></audio>
                <div
                    class="player-progress-bar"
                    :class="{ 'is-dragging': dragFraction !== null }"
                    @pointerdown="onProgressPointerDown"
                    @pointermove="onProgressPointerMove"
                    @pointerup="onProgressPointerUp"
                    @pointercancel="onProgressPointerCancel"
                >
                    <div
                        class="player-progress-fill"
                        :style="{ width: (dragFraction !== null ? dragFraction * 100 : state.progressPercent.value) + '%' }"
                    ></div>
                    <span
                        v-if="dragFraction !== null"
                        class="player-progress-tooltip"
                        :style="{ left: dragFraction * 100 + '%' }"
                    >{{ dragTimeLabel }}</span>
                </div>
                <div class="reader-time-row">
                    <span class="player-time">{{ state.currentTimeLabel.value }}</span>
                    <span class="player-time">{{ state.durationLabel.value }}</span>
                </div>
                <div class="reader-player-ui">
                    <div class="reader-player-buttons">
                        <!-- 장 이동은 경전·고전처럼 장이 여러 개인 작품에서 주된 이동
                             수단인데, 그동안 "더보기" 시트 안에 2탭 깊이로 있었다.
                             10초 이동을 밀어내지는 않는다 — 목차 없는 개인 문서에서는
                             그쪽이 유일한 이동 수단이다. 거친 이동을 바깥, 미세한
                             이동을 안쪽에 둬서 손가락 위치와 이동 폭을 맞춘다. -->
                        <button
                            v-if="state.headings.value.length > 1"
                            class="btn-player-chapter"
                            aria-label="이전 장"
                            type="button"
                            @click="logic.goToChapter(-1)"
                        >
                            <i data-lucide="chevron-first"></i>
                        </button>
                        <button class="btn-player-skip" aria-label="10초 뒤로" type="button" @click="controlsLogic.skipBack">
                            <i data-lucide="skip-back"></i>
                        </button>
                        <button class="btn-player-play" aria-label="재생 또는 일시정지" type="button" @click="logic.togglePlayPause">
                            <svg v-show="!state.isPlaying.value" xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="currentColor" stroke="none"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
                            <svg v-show="state.isPlaying.value" xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="currentColor" stroke="none"><rect x="6" y="4" width="4" height="16"></rect><rect x="14" y="4" width="4" height="16"></rect></svg>
                        </button>
                        <button class="btn-player-skip" aria-label="10초 앞으로" type="button" @click="controlsLogic.skipForward">
                            <i data-lucide="skip-forward"></i>
                        </button>
                        <button
                            v-if="state.headings.value.length > 1"
                            class="btn-player-chapter"
                            aria-label="다음 장"
                            type="button"
                            @click="logic.goToChapter(1)"
                        >
                            <i data-lucide="chevron-last"></i>
                        </button>
                    </div>
                    <ReaderControlsView :state="controlsState" :logic="controlsLogic" />
                </div>
            </footer>
        </div>
    </div>

    <IndexSheetView :state="state" :logic="logic" />
    <BookmarkSheetView :state="state" :logic="logic" />
    <ReaderMoreSheetView :state="state" :logic="logic" :on-share-click="onShareClick" />
    <ReaderSettingsSheetView :state="state" :logic="logic" :controls-logic="controlsLogic" :theme-logic="themeLogic" />
    <ReaderOptionsSheetView :state="controlsState" :logic="controlsLogic" />
    <ReaderPlaylistSheetView :state="state" :logic="logic" :audio-list-state="audioListState" />
</template>
