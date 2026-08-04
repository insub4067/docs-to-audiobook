<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
import { useSwipeToDismiss } from "../utils/swipeToDismiss";
import { useNewsUploadSheetState } from "./NewsUploadSheet_State.vue";
import { useNewsUploadSheetLogic } from "./NewsUploadSheet_Logic.vue";

const state = useNewsUploadSheetState();
const logic = useNewsUploadSheetLogic(state);

const sheet = ref<HTMLElement | null>(null);
useSwipeToDismiss(sheet, () => logic.close());

const textarea = ref<HTMLTextAreaElement | null>(null);

watch(() => state.isOpen.value, (open) => {
    document.body.style.overflow = open ? "hidden" : "";
    if (open) nextTick(() => textarea.value?.focus());
});

function onBackdropClick(event: MouseEvent): void {
    if (event.target === event.currentTarget) logic.close();
}
</script>

<template>
    <div
        class="action-sheet-backdrop"
        :class="{ show: state.isOpen.value }"
        role="dialog"
        aria-modal="true"
        aria-label="경제 뉴스 추가"
        @click="onBackdropClick"
    >
        <div class="action-sheet text-input-sheet" ref="sheet">
            <div class="action-sheet-handle"></div>
            <div class="index-sheet-header">
                <h3>경제 뉴스 추가</h3>
                <p class="action-sheet-subtitle">[{"title":"...", "content":"...", "category":"...", "source":"..."}] 형식의 JSON 배열을 붙여넣으세요</p>
            </div>
            <textarea
                ref="textarea"
                class="text-input-textarea"
                placeholder='[{"title": "뉴스 제목", "content": "요약 본문", "category": "경제", "source": "Reuters"}]'
                v-model="state.text.value"
            ></textarea>
            <p v-if="state.status.value" class="action-sheet-hint">{{ state.status.value }}</p>
            <button
                class="action-sheet-btn action-sheet-btn-primary"
                type="button"
                :disabled="!state.text.value.trim() || state.submitting.value"
                @click="logic.submit"
            >
                <i data-lucide="arrow-up-circle"></i>
                {{ state.submitting.value ? "등록 중..." : "등록하기" }}
            </button>
            <button class="action-sheet-btn action-sheet-btn-cancel" type="button" @click="logic.close">닫기</button>
        </div>
    </div>
</template>
