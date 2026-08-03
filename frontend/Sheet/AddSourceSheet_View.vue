<script setup lang="ts">
import { ref, watch } from "vue";
import type { GenerationState } from "../Generation/Generation_State.vue";
import type { GenerationLogic } from "../Generation/Generation_Logic.vue";
import { useSwipeToDismiss } from "../utils/swipeToDismiss";

const props = defineProps<{
    state: GenerationState;
    logic: GenerationLogic;
    onSelectFile: () => void;
}>();

const sheet = ref<HTMLElement | null>(null);
useSwipeToDismiss(sheet, () => props.logic.closeAddSourceSheet());

watch(() => props.state.addSourceMode.value, (mode) => {
    document.body.style.overflow = mode ? "hidden" : "";
});

function onBackdropClick(event: MouseEvent): void {
    if (event.target === event.currentTarget) props.logic.closeAddSourceSheet();
}

function onSelectFileClick(): void {
    props.logic.closeAddSourceSheet();
    props.onSelectFile();
}

function onUrlKeydown(event: KeyboardEvent): void {
    if (event.key === "Enter") {
        event.preventDefault();
        props.logic.fetchTextFromUrl();
    }
}

function onYoutubeKeydown(event: KeyboardEvent): void {
    if (event.key === "Enter") {
        event.preventDefault();
        props.logic.fetchTextFromYoutube();
    }
}
</script>

<template>
    <div
        class="action-sheet-backdrop"
        :class="{ show: !!state.addSourceMode.value }"
        role="dialog"
        aria-modal="true"
        aria-label="문서 추가"
        @click="onBackdropClick"
    >
        <div class="action-sheet" ref="sheet">
            <div class="action-sheet-handle"></div>

            <template v-if="state.addSourceMode.value === 'menu'">
                <div class="index-sheet-header">
                    <h3>문서 추가</h3>
                </div>
                <button class="action-sheet-btn" type="button" @click="onSelectFileClick">
                    <i data-lucide="file-up"></i>
                    파일 업로드
                </button>
                <button class="action-sheet-btn" type="button" @click="logic.selectLinkMode">
                    <i data-lucide="link"></i>
                    링크(기사, 블로그)에서 가져오기
                </button>
                <button class="action-sheet-btn" type="button" @click="logic.selectPasteMode">
                    <i data-lucide="clipboard-paste"></i>
                    텍스트 붙여넣기
                </button>
                <button class="action-sheet-btn" type="button" @click="logic.selectYoutubeMode">
                    <i data-lucide="clapperboard"></i>
                    유튜브
                </button>
                <button class="action-sheet-btn action-sheet-btn-cancel" type="button" @click="logic.closeAddSourceSheet">닫기</button>
            </template>

            <template v-else-if="state.addSourceMode.value === 'url'">
                <div class="index-sheet-header">
                    <h3>링크에서 가져오기</h3>
                </div>
                <div class="sheet-input-body">
                    <input
                        type="url"
                        inputmode="url"
                        placeholder="뉴스 기사나 커뮤니티 게시글 링크를 붙여넣으세요"
                        v-model="state.urlInputValue.value"
                        @keydown="onUrlKeydown"
                    >
                    <button
                        type="button"
                        class="btn-url-fetch btn-url-fetch-block"
                        :class="{ 'is-loading': state.isUrlFetchBusy.value }"
                        :disabled="state.isUrlFetchBusy.value"
                        @click="logic.fetchTextFromUrl"
                    >
                        <span>{{ state.isUrlFetchBusy.value ? "가져오는 중..." : "가져오기" }}</span>
                    </button>
                </div>
                <button class="action-sheet-btn action-sheet-btn-cancel" type="button" @click="logic.closeAddSourceSheet">닫기</button>
            </template>

            <template v-else-if="state.addSourceMode.value === 'youtube'">
                <div class="index-sheet-header">
                    <h3>유튜브</h3>
                </div>
                <div class="sheet-input-body">
                    <input
                        type="url"
                        inputmode="url"
                        placeholder="유튜브 영상 링크를 붙여넣으세요"
                        v-model="state.youtubeInputValue.value"
                        @keydown="onYoutubeKeydown"
                    >
                    <button
                        type="button"
                        class="btn-url-fetch btn-url-fetch-block"
                        :class="{ 'is-loading': state.isYoutubeFetchBusy.value }"
                        :disabled="state.isYoutubeFetchBusy.value"
                        @click="logic.fetchTextFromYoutube"
                    >
                        <span>{{ state.isYoutubeFetchBusy.value ? "가져오는 중..." : "가져오기" }}</span>
                    </button>
                </div>
                <button class="action-sheet-btn action-sheet-btn-cancel" type="button" @click="logic.closeAddSourceSheet">닫기</button>
            </template>

            <template v-else-if="state.addSourceMode.value === 'paste'">
                <div class="index-sheet-header">
                    <h3>텍스트 붙여넣기</h3>
                </div>
                <div class="sheet-input-body">
                    <textarea
                        rows="6"
                        placeholder="여기에 텍스트를 직접 붙여넣으세요"
                        v-model="state.pasteTextValue.value"
                    ></textarea>
                    <button
                        type="button"
                        class="btn-url-fetch btn-url-fetch-block"
                        :class="{ 'is-loading': state.isPasteBusy.value }"
                        :disabled="state.isPasteBusy.value"
                        @click="logic.pasteText"
                    >
                        <span>{{ state.isPasteBusy.value ? "처리 중..." : "사용하기" }}</span>
                    </button>
                </div>
                <button class="action-sheet-btn action-sheet-btn-cancel" type="button" @click="logic.closeAddSourceSheet">닫기</button>
            </template>
        </div>
    </div>
</template>
