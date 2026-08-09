<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { GenerationState } from "../../Generation/Generation_State.vue";
import type { GenerationLogic } from "../../Generation/Generation_Logic.vue";

const props = defineProps<{
    state: GenerationState;
    logic: GenerationLogic;
}>();

// 파일을 보내는 동안은 진행률을 실측할 수 있다(XHR upload.onprogress).
// 다 보낸 뒤 서버가 텍스트를 뽑는 구간은 알 수 없다 — 응답이 한 번에 오고
// 중간 상태를 스트리밍하지 않는다. 그 구간에 막대를 채우면 90%에서 멈춰
// 있는 흔한 거짓말이 되므로, 대신 경과 시간을 띄운다. 초가 올라가는 것만으로
// "멈추지 않았다"가 증명된다.
const LOADING_MESSAGES = [
    "내용을 분석하고 있습니다...",
    "페이지가 많거나 스캔 문서라면 1분 정도 걸릴 수 있어요",
    "텍스트를 정리하고 있습니다...",
];
const loadingMessageIndex = ref(0);
const elapsedSeconds = ref(0);
const isLoading = computed(() => props.state.isDropzoneLoading.value || props.state.isComposerBusy.value);

const uploadPercent = computed(() => props.state.uploadPercent.value);
const isSending = computed(() => uploadPercent.value !== null);

// 고성능 PDF는 OCR 구간에도 진짜 숫자가 있다(서버가 페이지 단위로 알려준다).
// 그 값이 있으면 경과 시간 대신 이걸 보여준다 — "45초째"보다 "12/30 페이지"가
// 얼마나 남았는지를 알려준다.
const pageProgress = computed(() => props.state.scanPageProgress.value);
const pagePercent = computed(() => {
    const progress = pageProgress.value;
    if (!progress || progress.total === 0) return 0;
    return Math.round((progress.done / progress.total) * 100);
});

const elapsedLabel = computed(() => {
    const minutes = Math.floor(elapsedSeconds.value / 60);
    const seconds = elapsedSeconds.value % 60;
    return minutes > 0 ? `${minutes}분 ${seconds}초째` : `${seconds}초째`;
});

let tickTimer: ReturnType<typeof setInterval> | null = null;

watch(isLoading, (loading) => {
    if (loading) {
        loadingMessageIndex.value = 0;
        elapsedSeconds.value = 0;
        // 타이머 하나로 경과 시간과 문구 교체를 함께 굴린다.
        tickTimer = setInterval(() => {
            elapsedSeconds.value += 1;
            loadingMessageIndex.value = Math.floor(elapsedSeconds.value / 4) % LOADING_MESSAGES.length;
        }, 1000);
    } else if (tickTimer) {
        clearInterval(tickTimer);
        tickTimer = null;
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

            <!-- 전송 중: 실측 진행률 -->
            <template v-if="isSending">
                <div
                    class="upload-progress-track"
                    role="progressbar"
                    aria-label="업로드 진행률"
                    :aria-valuenow="uploadPercent ?? 0"
                    aria-valuemin="0"
                    aria-valuemax="100"
                >
                    <div class="upload-progress-fill" :style="{ width: (uploadPercent ?? 0) + '%' }"></div>
                </div>
                <p class="upload-progress-label">파일을 보내는 중 {{ uploadPercent }}%</p>
            </template>

            <!-- 고성능 PDF: 서버가 페이지 단위로 알려주므로 여기도 실측이다 -->
            <template v-else-if="pageProgress">
                <div
                    class="upload-progress-track"
                    role="progressbar"
                    aria-label="문자 인식 진행률"
                    :aria-valuenow="pagePercent"
                    aria-valuemin="0"
                    aria-valuemax="100"
                >
                    <div class="upload-progress-fill" :style="{ width: pagePercent + '%' }"></div>
                </div>
                <p class="upload-progress-label">
                    글자를 읽는 중 {{ pageProgress.done }}/{{ pageProgress.total }}쪽
                </p>
                <p class="upload-elapsed">{{ elapsedLabel }}</p>
            </template>

            <!-- 그 밖의 서버 처리: 진행률을 알 수 없으므로 경과 시간만 -->
            <template v-else>
                <p>{{ LOADING_MESSAGES[loadingMessageIndex] }}</p>
                <p class="upload-elapsed">{{ elapsedLabel }}</p>
            </template>

            <p class="loading-overlay-warning">완료될 때까지 화면을 벗어나지 마세요</p>
            <button class="loading-cancel-btn" type="button" @click="logic.cancelUpload">취소</button>
        </div>
    </div>
</template>
