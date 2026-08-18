<script setup lang="ts">
import { ref, watch } from "vue";
import type { ReaderState } from "../Reader/Reader_State.vue";
import type { ReaderLogic } from "../Reader/Reader_Logic.vue";
import { useSwipeToDismiss } from "../utils/swipeToDismiss";

const props = defineProps<{
    state: ReaderState;
    logic: ReaderLogic;
    onShareClick: () => void;
}>();

const sheet = ref<HTMLElement | null>(null);
useSwipeToDismiss(sheet, () => props.logic.closeMoreSheet());

watch(() => props.state.isMoreSheetOpen.value, (open) => {
    document.body.style.overflow = open ? "hidden" : "";
});

function onBackdropClick(event: MouseEvent): void {
    if (event.target === event.currentTarget) props.logic.closeMoreSheet();
}

function onSettingsClick(): void {
    props.logic.closeMoreSheet();
    props.logic.openSettingsSheet();
}

function onIndexClick(): void {
    props.logic.closeMoreSheet();
    props.logic.openIndexSheet();
}

function onBookmarkClick(): void {
    props.logic.closeMoreSheet();
    props.logic.toggleBookmarkForCurrentSentence();
}

function onBookmarkListClick(): void {
    props.logic.closeMoreSheet();
    props.logic.openBookmarkSheet();
}

function onShareClickWrapped(): void {
    props.logic.closeMoreSheet();
    props.onShareClick();
}

function onSaveSharedClick(): void {
    props.logic.closeMoreSheet();
    props.logic.saveSharedAudiobook();
}

function onPlaylistClick(): void {
    props.logic.closeMoreSheet();
    props.logic.openPlaylistSheet();
}
</script>

<template>
    <div
        class="action-sheet-backdrop"
        :class="{ show: state.isMoreSheetOpen.value }"
        role="dialog"
        aria-modal="true"
        aria-label="읽기 화면 메뉴"
        @click="onBackdropClick"
    >
        <div class="action-sheet" ref="sheet">
            <div class="action-sheet-handle"></div>
            <button v-if="state.headings.value.length > 0" class="action-sheet-btn" type="button" @click="onIndexClick">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="8" y1="6" x2="21" y2="6"></line><line x1="8" y1="12" x2="21" y2="12"></line><line x1="8" y1="18" x2="21" y2="18"></line><line x1="3" y1="6" x2="3.01" y2="6"></line><line x1="3" y1="12" x2="3.01" y2="12"></line><line x1="3" y1="18" x2="3.01" y2="18"></line></svg>
                목차 보기
            </button>
            <button class="action-sheet-btn" type="button" @click="onBookmarkClick">
                <i data-lucide="bookmark"></i>
                이 문장 저장
            </button>
            <button class="action-sheet-btn" type="button" @click="onBookmarkListClick">
                <i data-lucide="bookmark-check"></i>
                저장한 문장
            </button>
            <button v-if="state.showShareBtn.value" class="action-sheet-btn" type="button" @click="onShareClickWrapped">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"></path><polyline points="16 6 12 2 8 6"></polyline><line x1="12" y1="2" x2="12" y2="15"></line></svg>
                공유하기
            </button>
            <button v-if="state.showSaveSharedBtn.value" class="action-sheet-btn" type="button" @click="onSaveSharedClick">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                내 오디오북에 저장
            </button>
            <button
                v-if="state.sharedPlaylistKind.value !== null || !!state.currentAudioObject.value?.folderId"
                class="action-sheet-btn"
                type="button"
                @click="onPlaylistClick"
            >
                <i data-lucide="list-music"></i>
                재생목록
            </button>
            <button class="action-sheet-btn" type="button" @click="onSettingsClick">
                <i data-lucide="settings-2"></i>
                읽기 설정
            </button>
            <button class="action-sheet-btn action-sheet-btn-cancel" type="button" @click="logic.closeMoreSheet">닫기</button>
        </div>
    </div>
</template>
