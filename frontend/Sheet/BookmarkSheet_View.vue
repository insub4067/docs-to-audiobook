<script setup lang="ts">
import { ref, watch } from "vue";
import type { ReaderState } from "../Reader/Reader_State.vue";
import type { ReaderLogic } from "../Reader/Reader_Logic.vue";
import type { BookmarkRecord } from "../services/bookmarks";
import { useSwipeToDismiss } from "../utils/swipeToDismiss";
import { formatTime } from "../utils/format";

const props = defineProps<{
    state: ReaderState;
    logic: ReaderLogic;
}>();

const sheet = ref<HTMLElement | null>(null);
useSwipeToDismiss(sheet, () => props.logic.closeBookmarkSheet());

watch(() => props.state.isBookmarkSheetOpen.value, (open) => {
    document.body.style.overflow = open ? "hidden" : "";
});

function onBackdropClick(event: MouseEvent): void {
    if (event.target === event.currentTarget) props.logic.closeBookmarkSheet();
}

function onRemove(bookmark: BookmarkRecord): void {
    props.logic.removeBookmark(bookmark);
}
</script>

<template>
    <div
        class="action-sheet-backdrop"
        :class="{ show: state.isBookmarkSheetOpen.value }"
        role="dialog"
        aria-modal="true"
        aria-label="저장한 문장"
        @click="onBackdropClick"
    >
        <div class="action-sheet index-sheet" ref="sheet">
            <div class="action-sheet-handle"></div>
            <div class="index-sheet-header">
                <h3>저장한 문장</h3>
            </div>

            <p v-if="state.bookmarks.value.length === 0" class="action-sheet-hint">
                아직 저장한 문장이 없어요. 듣다가 마음에 드는 문장에서 더보기 → "이 문장 저장"을 눌러 보세요.
            </p>

            <div v-else class="index-sheet-list">
                <div v-for="bookmark in state.bookmarks.value" :key="bookmark.sentenceIndex" class="bookmark-row">
                    <button type="button" class="bookmark-row-main" @click="logic.goToBookmark(bookmark)">
                        <span class="bookmark-row-text">{{ bookmark.text }}</span>
                        <span class="bookmark-row-time">{{ formatTime(bookmark.seconds) }}</span>
                    </button>
                    <button type="button" class="bookmark-row-remove" aria-label="저장 해제" @click.stop="onRemove(bookmark)">
                        <i data-lucide="trash-2"></i>
                    </button>
                </div>
            </div>

            <button class="action-sheet-btn action-sheet-btn-cancel" @click="logic.closeBookmarkSheet">닫기</button>
        </div>
    </div>
</template>
