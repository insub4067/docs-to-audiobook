<script setup lang="ts">
import { ref, watch } from "vue";
import type { ReaderState } from "../../composables/Reader/Reader_State.vue";
import type { ReaderLogic } from "../../composables/Reader/Reader_Logic.vue";
import { useSwipeToDismiss } from "../../utils/swipeToDismiss";

const props = defineProps<{
    state: ReaderState;
    logic: ReaderLogic;
}>();

const sheet = ref<HTMLElement | null>(null);

useSwipeToDismiss(sheet, () => props.logic.closeIndexSheet());

watch(() => props.state.isIndexSheetOpen.value, (open) => {
    document.body.style.overflow = open ? "hidden" : "";
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
            <div class="index-sheet-list">
                <div
                    v-for="heading in state.headings.value"
                    :key="heading.sentIndex"
                    :class="`index-item h${heading.level}`"
                    @click="logic.onHeadingClick(heading)"
                >{{ prefixFor(heading.level) }}{{ heading.text }}</div>
            </div>
            <button class="action-sheet-btn action-sheet-btn-cancel" @click="logic.closeIndexSheet">닫기</button>
        </div>
    </div>
</template>
