<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import HeaderView from "../components/Header/Header_View.vue";
import UploadView from "../components/Upload/Upload_View.vue";
import AddSourceSheetView from "../Sheet/AddSourceSheet_View.vue";
import TextInputSheetView from "../Sheet/TextInputSheet_View.vue";
import ScanTextSheetView from "../Sheet/ScanTextSheet_View.vue";
import GenerationModalView from "../Sheet/GenerationModal_View.vue";
import LoginPromptSheetView from "../Sheet/LoginPromptSheet_View.vue";
import AudioListView from "../components/Library/AudioList_View.vue";
import ReaderView from "../Reader/Reader_View.vue";
import TabBarView from "../components/TabBar/TabBar_View.vue";
import MyFilesView from "../Files/MyFiles_View.vue";
import { useGenerationState } from "../Generation/Generation_State.vue";
import { useGenerationLogic } from "../Generation/Generation_Logic.vue";
import { useVoiceState } from "../Voices/Voice_State.vue";
import { useVoiceLogic } from "../Voices/Voice_Logic.vue";
import { useAudioListState } from "../components/Library/AudioList_State.vue";
import { useAudioListLogic } from "../components/Library/AudioList_Logic.vue";
import type { AudiobookRecord } from "../services/indexedDb";
import { useReaderState } from "../Reader/Reader_State.vue";
import { useReaderLogic } from "../Reader/Reader_Logic.vue";
import { useReaderControlsState } from "../Reader/ReaderControls/ReaderControls_State.vue";
import { useReaderControlsLogic } from "../Reader/ReaderControls/ReaderControls_Logic.vue";
import { usePwaState } from "../components/Pwa/Pwa_State.vue";
import ThemeSheetView from "../Sheet/ThemeSheet_View.vue";
import { useThemeState } from "../Theme/Theme_State.vue";
import { useThemeLogic } from "../Theme/Theme_Logic.vue";
import { useMyFilesState } from "../Files/MyFiles_State.vue";
import { useMyFilesLogic } from "../Files/MyFiles_Logic.vue";
import { formatTime, getAudiobookDisplayTitle } from "../utils/format";
import { useAuthStore } from "../stores/auth";

const authStore = useAuthStore();
const pwaState = usePwaState();
const themeState = useThemeState();
const themeLogic = useThemeLogic(themeState);
const voiceState = useVoiceState();
const voiceLogic = useVoiceLogic(voiceState);
const generationState = useGenerationState();
const generationLogic = useGenerationLogic(generationState, voiceLogic);
const audioListState = useAudioListState();
const audioListLogic = useAudioListLogic(audioListState);
const myFilesState = useMyFilesState();
const myFilesLogic = useMyFilesLogic(myFilesState);

const readerState = useReaderState();
const readerControlsState = useReaderControlsState();
const readerControlsLogic = useReaderControlsLogic(readerControlsState, readerState.audioEl);
const readerLogic = useReaderLogic(readerState, readerControlsLogic, audioListLogic);

const activeTab = ref<"home" | "files">("home");

// 홈 화면은 "최근 추가"와 "즐겨찾기" 두 섹션만 일부만 — 전체 목록은
// 내 파일 탭에서 본다. 추가되거나 재생된 시각 중 더 최근인 순으로 정렬.
const RECENT_ITEMS_LIMIT = 3;
const BOOKMARKED_ITEMS_LIMIT = 5;
function recencyScore(audio: AudiobookRecord): number {
    return Math.max(audio.timestamp || 0, audio.playbackUpdatedAt || 0);
}
const recentItems = computed(() =>
    [...audioListState.savedAudiobooks.value]
        .sort((a, b) => recencyScore(b) - recencyScore(a))
        .slice(0, RECENT_ITEMS_LIMIT)
);
const bookmarkedItems = computed(() =>
    audioListState.savedAudiobooks.value
        .filter((a) => a.isBookmarked)
        .sort((a, b) => recencyScore(b) - recencyScore(a))
        .slice(0, BOOKMARKED_ITEMS_LIMIT)
);

// 재방문 사용자는 새 문서 추가보다 듣던 걸 이어 듣는 경우가 많아, 최근
// 재생한(그리고 충분히 진행된) 오디오북이 있으면 맨 위에 띄운다.
// 재생 시간(총 길이)은 저장돼 있지 않아 진행률(%)까진 못 보여주고,
// 지금까지 들은 위치만 보여준다.
const CONTINUE_LISTENING_MIN_SECONDS = 5;
const continueListeningItem = computed(() =>
    [...audioListState.savedAudiobooks.value]
        .filter((a) => (a.lastPosition || 0) > CONTINUE_LISTENING_MIN_SECONDS && a.playbackUpdatedAt)
        .sort((a, b) => (b.playbackUpdatedAt || 0) - (a.playbackUpdatedAt || 0))[0] ?? null
);

async function resumeListening(): Promise<void> {
    if (continueListeningItem.value) await audioListLogic.openItem(continueListeningItem.value);
}

function onEscape(event: KeyboardEvent): void {
    if (event.key !== "Escape") return;
    if (generationState.isLoginPromptOpen.value) generationState.isLoginPromptOpen.value = false;
    else if (readerLogic.closeIndexSheetIfOpen()) {
        // 목차 시트를 닫았다
    } else if (readerLogic.closeMoreSheetIfOpen()) {
        // 더보기 시트를 닫았다
    } else if (generationState.isModalOpen.value) generationLogic.closeModal();
}

function onImportLink(): void {
    const url = window.prompt("공유받은 링크를 붙여넣어 주세요:\n(예: https://.../share/...)");
    if (url) readerLogic.importSharedLink(url);
}

// 문서 추가 시트(AddSourceSheetView)와 그 안의 "파일 업로드" 버튼이 여는
// 실제 파일 입력창. 홈 탭이 아닐 때도(내 파일 화면의 "파일 추가"에서)
// 열려야 해서, 탭에 따라 v-show로 숨겨지는 <main> 안이 아니라 여기
// 최상위에 둔다 — 조상 요소가 display:none이면 숨겨진 input을 눌러도
// 파일 선택 창이 안 열리는 브라우저가 있다.
const fileInput = ref<HTMLInputElement | null>(null);

// 관리자는 PDF를 "고성능 PDF" 전용 메뉴(Vision OCR 강제)로만 받는다 —
// 일반 파일 업로드에서 빼서 헷갈리지 않게 한다. 관리자 전용 메뉴가 없는
// 일반 사용자는 그대로 파일 업로드로 PDF를 올릴 수 있어야 한다.
const fileInputAccept = computed(() =>
    authStore.isAdmin ? ".docx,.txt,.md,.markdown,.hwp" : ".docx,.pdf,.txt,.md,.markdown,.hwp"
);

function openFileInput(): void {
    fileInput.value?.click();
}

function onFileInputChange(event: Event): void {
    const files = (event.target as HTMLInputElement).files;
    if (files && files.length > 0) generationLogic.handleBatchFileSelect(files);
    (event.target as HTMLInputElement).value = "";
}

// 텍스트 스캔(OCR, 관리자 전용) 버튼이 여는 사진첩 입력 — 여러 장을
// 한 번에 골라 대기열에 담는다. fileInput과 같은 이유로 최상위에 둔다.
const imageInput = ref<HTMLInputElement | null>(null);

function openImageInput(): void {
    imageInput.value?.click();
}

function onImageInputChange(event: Event): void {
    const files = (event.target as HTMLInputElement).files;
    if (files) for (const file of files) generationLogic.addScannedImage(file);
    (event.target as HTMLInputElement).value = "";
}

// "고성능 PDF"(관리자 전용, Vision OCR 강제) 버튼이 여는 PDF 전용 입력.
const pdfInput = ref<HTMLInputElement | null>(null);

function openPdfInput(): void {
    pdfInput.value?.click();
}

function onPdfInputChange(event: Event): void {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (file) generationLogic.scanHighQualityPdf(file);
    (event.target as HTMLInputElement).value = "";
}

onMounted(async () => {
    document.addEventListener("keydown", onEscape);
    await voiceLogic.loadVoices();
    readerLogic.checkSharedLink();
});
</script>

<template>
    <HeaderView :theme-logic="themeLogic" :active-tab="activeTab" />
    <main class="app-main" id="appMain" v-show="activeTab === 'home'">
        <button
            v-if="continueListeningItem"
            type="button"
            class="glass-card continue-listening-card"
            @click="resumeListening"
        >
            <div class="continue-listening-icon"><i data-lucide="play"></i></div>
            <div class="continue-listening-info">
                <p class="continue-listening-label">이어 듣기</p>
                <p class="continue-listening-title">{{ getAudiobookDisplayTitle(continueListeningItem.title) }}</p>
                <p class="continue-listening-position">{{ formatTime(continueListeningItem.lastPosition || 0) }}부터</p>
            </div>
            <i data-lucide="chevron-right" class="continue-listening-chevron"></i>
        </button>
        <UploadView :state="generationState" :logic="generationLogic" />
        <AudioListView
            :state="audioListState"
            :logic="audioListLogic"
            :my-files-logic="myFilesLogic"
            :items="recentItems"
            title="최근 추가"
            :generating-items="generationState.generatingItems.value"
            :on-import-link="onImportLink"
        />
        <AudioListView
            v-if="bookmarkedItems.length > 0"
            :state="audioListState"
            :logic="audioListLogic"
            :my-files-logic="myFilesLogic"
            :items="bookmarkedItems"
            title="즐겨찾기"
            icon="star"
            :show-import-button="false"
            :show-generating-items="false"
            :auto-load="false"
            :hide-action-sheet="true"
            :generating-items="[]"
        />
    </main>
    <footer class="app-version-footer" v-show="activeTab === 'home'">
        <span>{{ pwaState.versionLabel.value }}</span>
    </footer>

    <MyFilesView
        v-show="activeTab === 'files'"
        :audio-list-state="audioListState"
        :audio-list-logic="audioListLogic"
        :my-files-state="myFilesState"
        :my-files-logic="myFilesLogic"
        :generation-logic="generationLogic"
        :generating-items="generationState.generatingItems.value"
    />

    <TabBarView v-show="!readerState.isOpen.value" :active-tab="activeTab" @select="(tab) => (activeTab = tab)" />

    <input
        ref="fileInput"
        type="file"
        :accept="fileInputAccept"
        multiple
        style="display: none;"
        @change="onFileInputChange"
    >
    <input
        ref="imageInput"
        type="file"
        accept="image/*"
        multiple
        style="display: none;"
        @change="onImageInputChange"
    >
    <input
        ref="pdfInput"
        type="file"
        accept=".pdf"
        style="display: none;"
        @change="onPdfInputChange"
    >
    <AddSourceSheetView
        :state="generationState"
        :logic="generationLogic"
        :on-select-file="openFileInput"
        :on-select-high-quality-pdf="openPdfInput"
    />
    <TextInputSheetView :state="generationState" :logic="generationLogic" />
    <ScanTextSheetView :state="generationState" :logic="generationLogic" :on-add-photo="openImageInput" />
    <GenerationModalView :state="generationState" :logic="generationLogic" :voice-state="voiceState" :voice-logic="voiceLogic" />
    <LoginPromptSheetView :state="generationState" :logic="generationLogic" />
    <ReaderView
        :state="readerState"
        :logic="readerLogic"
        :controls-state="readerControlsState"
        :controls-logic="readerControlsLogic"
        :audio-list-logic="audioListLogic"
        :theme-logic="themeLogic"
    />
    <ThemeSheetView :state="themeState" :logic="themeLogic" />
</template>
