<script setup lang="ts">
import { computed } from "vue";
import type { GenerationState } from "../../Generation/Generation_State.vue";
import type { GenerationLogic } from "../../Generation/Generation_Logic.vue";

const props = defineProps<{
    state: GenerationState;
    logic: GenerationLogic;
}>();

const isMobileDevice = computed(() =>
    /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) || window.innerWidth <= 768
);

function onDrop(event: DragEvent): void {
    props.state.isDragOver.value = false;
    const files = event.dataTransfer?.files;
    if (files && files.length > 0) props.logic.handleBatchFileSelect(files);
}

// touchend는 터치가 시작된 요소에서 그대로 발생한다 — 드롭존을 짚고
// 아래로 스크롤하다 손을 떼도 여기서 끝난다. 움직인 거리를 재서, 스크롤
// 등 드래그였다면(임계값 이상 이동) 시트를 열지 않고 탭일 때만 연다.
const DROPZONE_TAP_THRESHOLD_PX = 10;
let dropzoneTouchStartX = 0;
let dropzoneTouchStartY = 0;
let dropzoneTouchMoved = false;

function onDropzoneTouchStart(event: TouchEvent): void {
    dropzoneTouchStartX = event.touches[0].clientX;
    dropzoneTouchStartY = event.touches[0].clientY;
    dropzoneTouchMoved = false;
}

function onDropzoneTouchMove(event: TouchEvent): void {
    const dx = event.touches[0].clientX - dropzoneTouchStartX;
    const dy = event.touches[0].clientY - dropzoneTouchStartY;
    if (Math.abs(dx) > DROPZONE_TAP_THRESHOLD_PX || Math.abs(dy) > DROPZONE_TAP_THRESHOLD_PX) {
        dropzoneTouchMoved = true;
    }
}

function onDropzoneTouchEnd(event: TouchEvent): void {
    if (dropzoneTouchMoved) return;
    event.preventDefault();
    props.logic.openAddSourceMenu();
}
</script>

<template>
    <section class="glass-card upload-section">
        <div class="card-header">
            <i data-lucide="file-up" class="header-icon"></i>
            <h2>문서 업로드</h2>
        </div>

        <div
            class="upload-dropzone"
            :class="{ dragover: state.isDragOver.value }"
            @click="logic.openAddSourceMenu"
            @touchstart="onDropzoneTouchStart"
            @touchmove="onDropzoneTouchMove"
            @touchend="onDropzoneTouchEnd"
            @dragenter.prevent.stop="state.isDragOver.value = true"
            @dragover.prevent.stop="state.isDragOver.value = true"
            @dragleave.prevent.stop="state.isDragOver.value = false"
            @drop.prevent.stop="onDrop"
        >
            <div v-show="!state.isDropzoneLoading.value && !state.isComposerBusy.value">
                <i data-lucide="upload-cloud" class="dropzone-icon"></i>
                <p class="dropzone-text">{{ isMobileDevice ? "이곳을 터치하여 문서를 추가하세요" : "파일을 끌어다 놓거나 터치하여 추가 방법을 선택하세요" }}</p>
                <p class="dropzone-hint">파일 업로드 · 링크 · 텍스트 붙여넣기 지원</p>
            </div>

            <div v-show="state.isDropzoneLoading.value || state.isComposerBusy.value" style="text-align: center; color: var(--text-muted);">
                <div class="spinner-container" style="width: 32px; height: 32px; margin: 0 auto 12px;">
                    <div class="double-bounce1"></div>
                    <div class="double-bounce2"></div>
                </div>
                <p style="font-size: 15px; font-weight: 500;">문서를 분석하고 있습니다...</p>
            </div>
        </div>
    </section>
</template>
