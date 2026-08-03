<script setup lang="ts">
import { onMounted, onUnmounted, ref, type ComponentPublicInstance } from "vue";
import type { ReaderState } from "./Reader_State.vue";
import type { ReaderLogic } from "./Reader_Logic.vue";
import type { ReaderControlsState } from "./ReaderControls/ReaderControls_State.vue";
import type { ReaderControlsLogic } from "./ReaderControls/ReaderControls_Logic.vue";
import type { AudioListLogic } from "../components/Library/AudioList_Logic.vue";
import ReaderControlsView from "./ReaderControls/ReaderControls_View.vue";
import IndexSheetView from "../Sheet/IndexSheet_View.vue";
import ReaderMoreSheetView from "../Sheet/ReaderMoreSheet_View.vue";
import ReaderOptionsSheetView from "../Sheet/ReaderOptionsSheet_View.vue";
import type { ThemeLogic } from "../Theme/Theme_Logic.vue";
import { useSwipeToDismiss } from "../utils/swipeToDismiss";

const props = defineProps<{
    state: ReaderState;
    logic: ReaderLogic;
    controlsState: ReaderControlsState;
    controlsLogic: ReaderControlsLogic;
    audioListLogic: AudioListLogic;
    themeLogic: ThemeLogic;
}>();

function onShareClick(): void {
    const audio = props.state.currentAudioObject.value;
    if (audio) props.audioListLogic.performShare(audio);
}

function onProgressBarClick(event: MouseEvent): void {
    const bar = event.currentTarget as HTMLElement;
    const rect = bar.getBoundingClientRect();
    if (rect.width > 0) props.logic.seekTo((event.clientX - rect.left) / rect.width);
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
                <button class="btn-reader-close" aria-label="오디오북 듣기 닫기" title="오디오북 듣기 닫기" type="button" @click="logic.closeReader">
                    <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>
                </button>
                <h3 class="reader-book-title">{{ state.title.value }}</h3>
                <button class="btn-reader-close" aria-label="더보기" title="더보기" type="button" @click="logic.openMoreSheet">
                    <i data-lucide="more-horizontal"></i>
                </button>
            </header>

            <div
                class="reader-content"
                :ref="setContentEl"
                :style="{
                    fontFamily: controlsState.fontFamily.value === 'sans' ? 'var(--font-sans)' : 'var(--font-serif)',
                    '--reader-font-scale': controlsState.fontSize.value,
                }"
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

            <footer class="reader-controls">
                <audio :ref="setAudioEl"></audio>
                <div class="player-progress-bar" @click="onProgressBarClick">
                    <div class="player-progress-fill" :style="{ width: state.progressPercent.value + '%' }"></div>
                </div>
                <div class="reader-time-row">
                    <span class="player-time">{{ state.currentTimeLabel.value }}</span>
                    <span class="player-time">{{ state.durationLabel.value }}</span>
                </div>
                <div class="reader-player-ui">
                    <div class="reader-player-buttons">
                        <button class="btn-player-skip" aria-label="10초 뒤로" title="10초 뒤로" type="button" @click="controlsLogic.skipBack">
                            <i data-lucide="skip-back"></i>
                        </button>
                        <button class="btn-player-play" aria-label="재생 또는 일시정지" title="재생 또는 일시정지" type="button" @click="logic.togglePlayPause">
                            <svg v-show="!state.isPlaying.value" xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="currentColor" stroke="none"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
                            <svg v-show="state.isPlaying.value" xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="currentColor" stroke="none"><rect x="6" y="4" width="4" height="16"></rect><rect x="14" y="4" width="4" height="16"></rect></svg>
                        </button>
                        <button class="btn-player-skip" aria-label="10초 앞으로" title="10초 앞으로" type="button" @click="controlsLogic.skipForward">
                            <i data-lucide="skip-forward"></i>
                        </button>
                    </div>
                    <ReaderControlsView :state="controlsState" :logic="controlsLogic" />
                </div>
            </footer>
        </div>
    </div>

    <IndexSheetView :state="state" :logic="logic" />
    <ReaderMoreSheetView :state="state" :logic="logic" :controls-logic="controlsLogic" :theme-logic="themeLogic" :on-share-click="onShareClick" />
    <ReaderOptionsSheetView :state="controlsState" :logic="controlsLogic" />
</template>
