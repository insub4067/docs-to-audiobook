<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { GenerationState } from "../../Generation/Generation_State.vue";

const props = defineProps<{
    state: GenerationState;
}>();

// 고성능 PDF(페이지별 OCR)처럼 오래 걸리는 처리 중에 화면이 멈춘 것처럼
// 보이지 않도록, 정적인 문구 대신 몇 초마다 바뀌는 문구를 보여준다.
// 실제 단계 진행률은 서버가 한 번의 응답으로만 결과를 주기 때문에
// 알 수 없어(중간 진행 상황을 스트리밍하지 않음), 정직하게 "시간이
// 걸릴 수 있다"는 것만 안내한다.
const LOADING_MESSAGES = [
    "문서를 업로드하고 있습니다...",
    "내용을 분석하고 있습니다...",
    "페이지가 많거나 스캔 문서라면 1분 정도 걸릴 수 있어요",
    "텍스트를 정리하고 있습니다...",
];
const loadingMessageIndex = ref(0);
const isLoading = computed(() => props.state.isDropzoneLoading.value || props.state.isComposerBusy.value);
let loadingMessageTimer: ReturnType<typeof setInterval> | null = null;

watch(isLoading, (loading) => {
    if (loading) {
        loadingMessageIndex.value = 0;
        loadingMessageTimer = setInterval(() => {
            loadingMessageIndex.value = (loadingMessageIndex.value + 1) % LOADING_MESSAGES.length;
        }, 3500);
    } else if (loadingMessageTimer) {
        clearInterval(loadingMessageTimer);
        loadingMessageTimer = null;
    }
});
</script>

<template>
    <div class="loading-overlay" :class="{ show: isLoading }" role="alert" aria-live="assertive">
        <div class="loading-card">
            <div class="spinner-container">
                <div class="double-bounce1"></div>
                <div class="double-bounce2"></div>
            </div>
            <h3>업로드하고 있어요</h3>
            <p>{{ LOADING_MESSAGES[loadingMessageIndex] }}</p>
            <p class="loading-overlay-warning">완료될 때까지 화면을 벗어나지 마세요</p>
        </div>
    </div>
</template>
