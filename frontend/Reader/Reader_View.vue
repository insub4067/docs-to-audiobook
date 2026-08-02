<script setup lang="ts">
import { onMounted, onUnmounted, type ComponentPublicInstance } from "vue";
import type { ReaderState } from "./Reader_State.vue";
import type { ReaderLogic } from "./Reader_Logic.vue";
import type { ReaderControlsState } from "./ReaderControls/ReaderControls_State.vue";
import type { ReaderControlsLogic } from "./ReaderControls/ReaderControls_Logic.vue";
import type { AudioListLogic } from "../components/Library/AudioList_Logic.vue";
import ReaderControlsView from "./ReaderControls/ReaderControls_View.vue";
import IndexSheetView from "../Sheet/IndexSheet_View.vue";
import ReaderOptionsSheetView from "../Sheet/ReaderOptionsSheet_View.vue";

const props = defineProps<{
    state: ReaderState;
    logic: ReaderLogic;
    controlsState: ReaderControlsState;
    controlsLogic: ReaderControlsLogic;
    audioListLogic: AudioListLogic;
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

let detachUiCollapseHandlers: (() => void) | null = null;
onMounted(() => { detachUiCollapseHandlers = props.logic.attachUiCollapseHandlers(); });
onUnmounted(() => detachUiCollapseHandlers?.());
</script>

<template>
    <div class="reader-overlay" :class="{ show: state.isOpen.value }" role="dialog" aria-modal="true" aria-label="오디오북 듣기">
        <div class="reader-container" :ref="setContainerEl">
            <header class="reader-header">
                <h3 class="reader-book-title">{{ state.title.value }}</h3>
                <div class="reader-header-actions" style="display: flex; gap: 8px;">
                    <button
                        class="btn-reader-close"
                        aria-label="목차 보기"
                        title="목차 보기"
                        type="button"
                        :style="{ display: state.headings.value.length > 0 ? 'flex' : 'none' }"
                        @click="logic.openIndexSheet"
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="8" y1="6" x2="21" y2="6"></line><line x1="8" y1="12" x2="21" y2="12"></line><line x1="8" y1="18" x2="21" y2="18"></line><line x1="3" y1="6" x2="3.01" y2="6"></line><line x1="3" y1="12" x2="3.01" y2="12"></line><line x1="3" y1="18" x2="3.01" y2="18"></line></svg>
                    </button>
                    <button
                        class="btn-reader-close"
                        aria-label="공유하기"
                        title="공유하기"
                        type="button"
                        :style="{ display: state.showShareBtn.value ? 'flex' : 'none' }"
                        @click="onShareClick"
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"></path><polyline points="16 6 12 2 8 6"></polyline><line x1="12" y1="2" x2="12" y2="15"></line></svg>
                    </button>
                    <button
                        class="btn-reader-close"
                        aria-label="내 오디오북에 저장"
                        title="내 오디오북에 저장"
                        :style="{ display: state.showSaveSharedBtn.value ? 'flex' : 'none' }"
                        @click="logic.saveSharedAudiobook"
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                    </button>
                    <button class="btn-reader-close" aria-label="오디오북 듣기 닫기" title="오디오북 듣기 닫기" type="button" @click="logic.closeReader">
                        <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                    </button>
                </div>
            </header>

            <div class="reader-content" :ref="setContentEl">
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
    <ReaderOptionsSheetView :state="controlsState" :logic="controlsLogic" />
</template>
