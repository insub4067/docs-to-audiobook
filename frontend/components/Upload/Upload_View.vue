<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import type { GenerationState } from "../../composables/Generation/Generation_State.vue";
import type { GenerationLogic } from "../../composables/Generation/Generation_Logic.vue";

const props = defineProps<{
    state: GenerationState;
    logic: GenerationLogic;
}>();

const fileInput = ref<HTMLInputElement | null>(null);
const urlInput = ref<HTMLInputElement | null>(null);

const isMobileDevice = computed(() =>
    /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) || window.innerWidth <= 768
);

function openFileInput(): void {
    fileInput.value?.click();
}

function onFileInputChange(event: Event): void {
    const files = (event.target as HTMLInputElement).files;
    if (files && files.length > 0) props.logic.handleBatchFileSelect(files);
    (event.target as HTMLInputElement).value = "";
}

function onDrop(event: DragEvent): void {
    props.state.isDragOver.value = false;
    const files = event.dataTransfer?.files;
    if (files && files.length > 0) props.logic.handleBatchFileSelect(files);
}

function onUrlKeydown(event: KeyboardEvent): void {
    if (event.key === "Enter") {
        event.preventDefault();
        props.logic.fetchTextFromUrl();
    }
}

function clearUrlInput(): void {
    props.state.urlInputValue.value = "";
    urlInput.value?.focus();
}

onMounted(() => {
    document.addEventListener("pointerdown", (event) => {
        if (document.activeElement === urlInput.value && !(event.target as HTMLElement).closest(".url-input-row")) {
            urlInput.value?.blur();
        }
    });
});
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
            @click="openFileInput"
            @touchend.prevent="openFileInput"
            @dragenter.prevent.stop="state.isDragOver.value = true"
            @dragover.prevent.stop="state.isDragOver.value = true"
            @dragleave.prevent.stop="state.isDragOver.value = false"
            @drop.prevent.stop="onDrop"
        >
            <input
                ref="fileInput"
                type="file"
                accept=".docx,.pdf,.txt,.md,.markdown,.hwp"
                multiple
                style="display: none;"
                @change="onFileInputChange"
                @click.stop
            >
            <div v-show="!state.isDropzoneLoading.value">
                <i data-lucide="upload-cloud" class="dropzone-icon"></i>
                <p class="dropzone-text">{{ isMobileDevice ? "이곳을 터치하여 문서를 업로드하세요" : "파일을 이곳에 끌어다 놓거나 터치하세요" }}</p>
                <p class="dropzone-hint">{{ isMobileDevice ? "지원: DOCX, PDF, TXT, MD, HWP" : "지원 파일: DOCX, PDF, TXT, MD, HWP (최대 10MB, 복수 선택 가능)" }}</p>
            </div>

            <div v-show="state.isDropzoneLoading.value" style="text-align: center; color: var(--text-muted);">
                <div class="spinner-container" style="width: 32px; height: 32px; margin: 0 auto 12px;">
                    <div class="double-bounce1"></div>
                    <div class="double-bounce2"></div>
                </div>
                <p style="font-size: 15px; font-weight: 500;">문서를 분석하고 있습니다...</p>
            </div>
        </div>

        <div class="url-divider"><span>또는</span></div>

        <div class="url-input-row">
            <div class="url-input-wrapper">
                <input
                    ref="urlInput"
                    type="url"
                    placeholder="뉴스 기사나 커뮤니티 게시글 링크를 붙여넣으세요"
                    inputmode="url"
                    v-model="state.urlInputValue.value"
                    @keydown="onUrlKeydown"
                >
                <button
                    type="button"
                    class="btn-url-clear"
                    aria-label="링크 입력 지우기"
                    :hidden="state.urlInputValue.value.length === 0"
                    @click="clearUrlInput"
                >&times;</button>
            </div>
            <button
                type="button"
                class="btn-url-fetch"
                :class="{ 'is-loading': state.isUrlFetchBusy.value }"
                :disabled="state.isUrlFetchBusy.value"
                @click="logic.fetchTextFromUrl"
            >
                <i data-lucide="link"></i>
                <span>{{ state.isUrlFetchBusy.value ? "가져오는 중..." : "가져오기" }}</span>
            </button>
        </div>
    </section>
</template>
