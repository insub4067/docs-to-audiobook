<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import HeaderView from "../components/Header/Header_View.vue";
import UploadView from "../components/Upload/Upload_View.vue";
import UploadBlockingOverlayView from "../components/Upload/UploadBlockingOverlay_View.vue";
import AuthLoadingOverlayView from "../Auth/AuthLoadingOverlay_View.vue";
import AddSourceSheetView from "../Sheet/AddSourceSheet_View.vue";
import TextInputSheetView from "../Sheet/TextInputSheet_View.vue";
import NewsUploadSheetView from "../Sheet/NewsUploadSheet_View.vue";
import LibraryUploadSheetView from "../Sheet/LibraryUploadSheet_View.vue";
import ScanTextSheetView from "../Sheet/ScanTextSheet_View.vue";
import GenerationModalView from "../Sheet/GenerationModal_View.vue";
import LoginPromptSheetView from "../Sheet/LoginPromptSheet_View.vue";
import PromptSheetView from "../Sheet/PromptSheet_View.vue";
import { usePromptSheetState } from "../Sheet/PromptSheet_State.vue";
import { usePromptSheetLogic } from "../Sheet/PromptSheet_Logic.vue";
import AudioListView from "../components/Library/AudioList_View.vue";
import ReaderView from "../Reader/Reader_View.vue";
import TabBarView from "../components/TabBar/TabBar_View.vue";
import MiniPlayerView from "../components/MiniPlayer/MiniPlayer_View.vue";
import MyFilesView from "../Files/MyFiles_View.vue";
import TodayNewsView from "../components/News/TodayNews_View.vue";
import NewsListSheetView from "../components/News/NewsListSheet_View.vue";
import LibraryView from "../Library/Library_View.vue";
import LibraryDetailView from "../Library/LibraryDetail_View.vue";
import { useLibraryState } from "../Library/Library_State.vue";
import { useLibraryLogic } from "../Library/Library_Logic.vue";
import { useGenerationState } from "../Generation/Generation_State.vue";
import { useGenerationLogic } from "../Generation/Generation_Logic.vue";
import { useVoiceState } from "../Voices/Voice_State.vue";
import { useVoiceLogic } from "../Voices/Voice_Logic.vue";
import { useAudioListState } from "../components/Library/AudioList_State.vue";
import { useAudioListLogic } from "../components/Library/AudioList_Logic.vue";
import { getAllAudiobooksFromDB, type AudiobookRecord } from "../services/indexedDb";
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
const promptSheetState = usePromptSheetState();
const promptSheetLogic = usePromptSheetLogic(promptSheetState);
const libraryState = useLibraryState();
const libraryLogic = useLibraryLogic(libraryState, readerLogic);

const activeTab = ref<"home" | "library" | "files">("home");

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

// 읽기 화면을 닫아도(뒤로 가기) 재생이 계속되면 탭바 위에 미니 플레이어를
// 띄운다 — 목록 마지막 줄이 그 밑에 가리지 않게 스크롤 영역에 여유를 준다.
const hasMiniPlayer = computed(() => !readerState.isOpen.value && !!readerState.title.value);

function onEscape(event: KeyboardEvent): void {
    if (event.key !== "Escape") return;
    if (generationState.isLoginPromptOpen.value) generationState.isLoginPromptOpen.value = false;
    else if (readerLogic.closeIndexSheetIfOpen()) {
        // 목차 시트를 닫았다
    } else if (readerLogic.closeSettingsSheetIfOpen()) {
        // 읽기 설정 시트를 닫았다
    } else if (readerLogic.closeMoreSheetIfOpen()) {
        // 더보기 시트를 닫았다
    } else if (readerLogic.closePlaylistSheetIfOpen()) {
        // 재생목록 시트를 닫았다
    } else if (libraryState.isDetailOpen.value) {
        libraryLogic.closeDetail();
    } else if (generationState.isModalOpen.value) generationLogic.closeModal();
}

async function onImportLink(): Promise<void> {
    const url = await promptSheetLogic.showPrompt("공유받은 링크를 붙여넣어 주세요", { subtitle: "예: https://.../share/..." });
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

// 미니 플레이어를 탭바 바로 위에 빈틈없이 붙이려면 탭바의 실제 렌더 높이가
// 필요하다 — 76px 같은 상수는 safe-area가 얼마나 이미 포함됐는지 기기마다
// 달라 미니 플레이어와 탭바 사이에 틈이 생겼다. 실제 높이를 재서 CSS
// 변수로 넘긴다(Reader의 --reader-header-h와 같은 방식). 폰트·아이콘이
// 늦게 로드되며 높이가 미세하게 바뀔 수 있어 ResizeObserver로 계속 맞춘다.
let tabBarResizeObserver: ResizeObserver | null = null;
function watchTabBarHeight(): void {
    const tabBar = document.querySelector<HTMLElement>(".tab-bar");
    if (!tabBar) return;
    document.documentElement.style.setProperty("--tab-bar-h", `${tabBar.offsetHeight}px`);
    tabBarResizeObserver = new ResizeObserver(() => {
        document.documentElement.style.setProperty("--tab-bar-h", `${tabBar.offsetHeight}px`);
    });
    tabBarResizeObserver.observe(tabBar);
}

// 마지막으로 듣던 오디오북이 있으면, 리더 화면을 펼치지 않고도 그 정보를
// 오디오 엘리먼트에 미리 실어 둔다 — PWA를 새로 열자마자 미니 플레이어에
// 제목/진행 상황이 바로 보이게 하기 위해서다(재생은 하지 않는다).
const CONTINUE_LISTENING_MIN_SECONDS = 5;
async function restoreLastPlayedSession(): Promise<void> {
    const audiobooks = await getAllAudiobooksFromDB();
    const lastPlayed = audiobooks
        .filter((a) => (a.lastPosition || 0) > CONTINUE_LISTENING_MIN_SECONDS && a.playbackUpdatedAt && a.audioData)
        .sort((a, b) => (b.playbackUpdatedAt || 0) - (a.playbackUpdatedAt || 0))[0];
    if (lastPlayed) readerLogic.restoreLastSession(lastPlayed);
}

onMounted(async () => {
    document.addEventListener("keydown", onEscape);
    watchTabBarHeight();
    await voiceLogic.loadVoices();
    readerLogic.checkSharedLink();
    restoreLastPlayedSession();
});
</script>

<template>
    <HeaderView :theme-logic="themeLogic" :active-tab="activeTab" />
    <main class="app-main" id="appMain" :class="{ 'has-mini-player': hasMiniPlayer }" v-show="activeTab === 'home'">
        <UploadView :state="generationState" :logic="generationLogic" />
        <TodayNewsView :logic="readerLogic" />
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
        <footer class="app-version-footer">
            <span>{{ pwaState.versionLabel.value }}</span>
        </footer>
    </main>

    <LibraryView v-show="activeTab === 'library'" :logic="readerLogic" :has-mini-player="hasMiniPlayer" />

    <MyFilesView
        v-show="activeTab === 'files'"
        :audio-list-state="audioListState"
        :audio-list-logic="audioListLogic"
        :my-files-state="myFilesState"
        :my-files-logic="myFilesLogic"
        :generation-logic="generationLogic"
        :generating-items="generationState.generatingItems.value"
        :has-mini-player="hasMiniPlayer"
        :reader-logic="readerLogic"
    />

    <TabBarView v-show="!readerState.isOpen.value" :active-tab="activeTab" @select="(tab) => (activeTab = tab)" />
    <MiniPlayerView :state="readerState" :logic="readerLogic" />

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
    <UploadBlockingOverlayView :state="generationState" :logic="generationLogic" />
    <AuthLoadingOverlayView />
    <ScanTextSheetView :state="generationState" :logic="generationLogic" :on-add-photo="openImageInput" />
    <GenerationModalView :state="generationState" :logic="generationLogic" :voice-state="voiceState" :voice-logic="voiceLogic" />
    <LoginPromptSheetView :state="generationState" :logic="generationLogic" />
    <ReaderView
        :state="readerState"
        :logic="readerLogic"
        :controls-state="readerControlsState"
        :controls-logic="readerControlsLogic"
        :audio-list-logic="audioListLogic"
        :audio-list-state="audioListState"
        :theme-logic="themeLogic"
    />
    <ThemeSheetView :state="themeState" :logic="themeLogic" />
    <PromptSheetView />
    <NewsListSheetView :logic="readerLogic" />
    <NewsUploadSheetView />
    <LibraryUploadSheetView />
    <LibraryDetailView :state="libraryState" :logic="libraryLogic" />
</template>
