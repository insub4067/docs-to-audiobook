<script setup lang="ts">
import { onUnmounted, ref, watch } from "vue";
import type { GenerationState } from "../Generation/Generation_State.vue";
import type { GenerationLogic } from "../Generation/Generation_Logic.vue";
import { useSwipeToDismiss } from "../utils/swipeToDismiss";

const props = defineProps<{
    state: GenerationState;
    logic: GenerationLogic;
    onAddPhoto: () => void;
}>();

const sheet = ref<HTMLElement | null>(null);
useSwipeToDismiss(sheet, () => props.logic.closeScanSheet());

watch(() => props.state.isScanSheetOpen.value, (open) => {
    document.body.style.overflow = open ? "hidden" : "";
});

// 촬영한 File은 같은 참조가 유지되는 동안 blob URL을 재사용하고, 목록에서
// 빠지면 즉시 해제한다 — 매번 새로 만들면 스캔을 여러 장 이어 찍을 때
// 메모리가 계속 쌓인다.
const urlCache = new Map<File, string>();
function urlFor(file: File): string {
    let url = urlCache.get(file);
    if (!url) {
        url = URL.createObjectURL(file);
        urlCache.set(file, url);
    }
    return url;
}
watch(() => props.state.scannedImages.value, (files) => {
    for (const [file, url] of urlCache) {
        if (!files.includes(file)) {
            URL.revokeObjectURL(url);
            urlCache.delete(file);
        }
    }
});
onUnmounted(() => {
    for (const url of urlCache.values()) URL.revokeObjectURL(url);
    urlCache.clear();
});

function onBackdropClick(event: MouseEvent): void {
    if (event.target === event.currentTarget) props.logic.closeScanSheet();
}
</script>

<template>
    <div
        class="action-sheet-backdrop"
        :class="{ show: state.isScanSheetOpen.value }"
        role="dialog"
        aria-modal="true"
        aria-label="텍스트 스캔"
        @click="onBackdropClick"
    >
        <div class="action-sheet" ref="sheet">
            <div class="action-sheet-handle"></div>
            <div class="index-sheet-header">
                <h3>텍스트 스캔</h3>
            </div>
            <p class="action-sheet-hint">사진첩에서 여러 장을 골라 순서대로 한 번에 추출할 수 있어요</p>

            <div class="scan-photo-grid">
                <div v-for="(image, index) in state.scannedImages.value" :key="index" class="scan-photo-thumb">
                    <img :src="urlFor(image)" :alt="`고른 사진 ${index + 1}`">
                    <button type="button" class="scan-photo-remove" aria-label="삭제" @click="logic.removeScannedImage(index)">
                        <i data-lucide="x"></i>
                    </button>
                    <span class="scan-photo-index">{{ index + 1 }}</span>
                </div>
                <button type="button" class="scan-photo-add" aria-label="사진첩에서 추가" @click="onAddPhoto">
                    <i data-lucide="image-plus"></i>
                </button>
            </div>

            <button
                class="action-sheet-btn action-sheet-btn-primary"
                type="button"
                :disabled="state.scannedImages.value.length === 0 || state.isComposerBusy.value"
                @click="logic.submitScannedImages"
            >
                <i data-lucide="scan-text"></i>
                {{ state.isComposerBusy.value ? "추출 중..." : `텍스트 추출하기 (${state.scannedImages.value.length}장)` }}
            </button>
            <button class="action-sheet-btn action-sheet-btn-cancel" type="button" @click="logic.closeScanSheet">닫기</button>
        </div>
    </div>
</template>
