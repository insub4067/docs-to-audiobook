<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
import { useSwipeToDismiss } from "../utils/swipeToDismiss";
import { useLibraryUploadSheetState } from "./LibraryUploadSheet_State.vue";
import { useLibraryUploadSheetLogic } from "./LibraryUploadSheet_Logic.vue";

const state = useLibraryUploadSheetState();
const logic = useLibraryUploadSheetLogic(state);

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
        aria-label="라이브러리 작품 추가"
        @click="onBackdropClick"
    >
        <div class="action-sheet text-input-sheet" ref="sheet">
            <div class="action-sheet-handle"></div>
            <div class="index-sheet-header">
                <h3>라이브러리 작품 추가</h3>
                <p class="action-sheet-subtitle">
                    title/content 필수, category·edition·translator·source·rights·description 선택,
                    status를 "published"로 명시해야 공개돼요(생략 시 검토 상태로 비공개 저장)
                </p>
            </div>
            <textarea
                ref="textarea"
                class="text-input-textarea"
                placeholder='[{"title": "도덕경", "category": "철학·사상", "edition": "왕필본", "rights": "원전 공개 이용 가능", "status": "published", "content": "# 1장\n..."}]'
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
