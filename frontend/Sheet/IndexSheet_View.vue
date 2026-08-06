<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import type { ReaderState } from "../Reader/Reader_State.vue";
import type { ReaderLogic } from "../Reader/Reader_Logic.vue";
import { useSwipeToDismiss } from "../utils/swipeToDismiss";

const props = defineProps<{
    state: ReaderState;
    logic: ReaderLogic;
}>();

const sheet = ref<HTMLElement | null>(null);
const list = ref<HTMLElement | null>(null);

useSwipeToDismiss(sheet, () => props.logic.closeIndexSheet());

const currentIndex = computed(() => props.logic.currentChapterIndex());

/** 장 길이는 다음 장 시작까지. 마지막 장은 총 재생시간까지다. */
function durationLabel(index: number): string {
    const headings = props.state.headings.value;
    const next = headings[index + 1];
    const endMs = next ? next.startMs : props.state.durationSeconds.value * 1000;
    const minutes = Math.round((endMs - headings[index].startMs) / 60000);
    if (!endMs || minutes < 0) return "";
    return minutes > 0 ? `${minutes}분` : "1분 미만";
}

watch(() => props.state.isIndexSheetOpen.value, async (open) => {
    document.body.style.overflow = open ? "hidden" : "";
    if (!open) return;
    // 81장짜리 도덕경이면 목차가 길다. 열자마자 지금 듣는 장이 보여야
    // 목차가 탐색 수단으로 쓸모가 있다.
    await nextTick();
    list.value?.querySelector(".is-current")?.scrollIntoView({ block: "center" });
});

function onBackdropClick(event: MouseEvent): void {
    if (event.target === event.currentTarget) props.logic.closeIndexSheet();
}

function prefixFor(level: number): string {
    return level === 1 ? "• " : level === 2 ? "└ " : "  └ ";
}
</script>

<template>
    <div
        class="action-sheet-backdrop"
        :class="{ show: state.isIndexSheetOpen.value }"
        role="dialog"
        aria-modal="true"
        aria-label="목차"
        @click="onBackdropClick"
    >
        <div class="action-sheet index-sheet" ref="sheet">
            <div class="action-sheet-handle"></div>
            <div class="index-sheet-header">
                <h3>목차 (Index)</h3>
            </div>
            <div class="index-sheet-list" ref="list">
                <div
                    v-for="(heading, index) in state.headings.value"
                    :key="heading.sentIndex"
                    class="index-item"
                    :class="[`h${heading.level}`, { 'is-current': index === currentIndex }]"
                    @click="logic.onHeadingClick(heading)"
                >
                    <span class="index-item-text">{{ prefixFor(heading.level) }}{{ heading.text }}</span>
                    <span v-if="durationLabel(index)" class="index-item-duration">{{ durationLabel(index) }}</span>
                </div>
            </div>
            <button class="action-sheet-btn action-sheet-btn-cancel" @click="logic.closeIndexSheet">닫기</button>
        </div>
    </div>
</template>
