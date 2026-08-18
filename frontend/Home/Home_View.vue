<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import HeaderView from "../components/Header/Header_View.vue";
import UploadView from "../components/Upload/Upload_View.vue";
import OnboardingView from "../components/Onboarding/Onboarding_View.vue";
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
import ProfileView from "../Profile/Profile_View.vue";
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

const activeTab = ref<"home" | "library" | "files" | "profile">("home");

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
const fileInputAccept = ".docx,.pdf,.txt,.md,.markdown,.hwp";

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
// 변수로 넘긴다(Reader의 --reader-header-h와 같은 방식).
//
// 헤더 높이는 프로필 탭의 로그아웃 버튼을 화면 맨 아래에 고정할 때,
// 미니 플레이어 높이는 그 버튼이 미니 플레이어에 가려지지 않게 할 때 쓴다.
function measureBarHeights(): void {
    const root = document.documentElement.style;
    const tabBar = document.querySelector<HTMLElement>(".tab-bar");
    const header = document.querySelector<HTMLElement>(".app-header");
    const miniPlayer = document.querySelector<HTMLElement>(".mini-player");
    if (tabBar) {
        const tabStyle = getComputedStyle(tabBar);
        const tabTotalH = tabBar.offsetHeight + parseFloat(tabStyle.marginTop) + parseFloat(tabStyle.marginBottom);
        root.setProperty("--tab-bar-h", `${tabTotalH}px`);
    }
    if (header) root.setProperty("--header-h", `${header.offsetHeight}px`);
    if (miniPlayer) {
        const mpStyle = getComputedStyle(miniPlayer);
        const mpTotalH = miniPlayer.offsetHeight + parseFloat(mpStyle.marginTop) + parseFloat(mpStyle.marginBottom);
        root.setProperty("--mini-player-h", `${mpTotalH}px`);
    }
}

// 폰트·아이콘이 늦게 로드되며 높이가 미세하게 바뀔 수 있어 계속 맞춘다.
// 미니 플레이어는 항상 마운트돼 있고(v-show가 아닌 opacity/transform으로
// 표시) 표시 여부와 무관하게 실제 렌더 높이를 잴 수 있다.
let barResizeObserver: ResizeObserver | null = null;
function watchBarHeights(): void {
    measureBarHeights();
    barResizeObserver = new ResizeObserver(measureBarHeights);
    for (const selector of [".tab-bar", ".app-header", ".mini-player"]) {
        const element = document.querySelector<HTMLElement>(selector);
        if (element) barResizeObserver.observe(element);
    }
}

// 화면이 숨겨져 있는 동안에는 브라우저가 렌더링 단계를 건너뛴다. 그래서
// 두 가지가 어긋난 채로 남는다 — ResizeObserver 콜백이 전달되지 않아
// 위 변수들이 낡은 값으로 굳고, 시작만 하고 진행되지 않은 CSS 전환이
// 그대로 멈춰 미니 플레이어가 반쯤 올라온 채로 굳는다(백그라운드에
// 있다가 PWA로 돌아왔을 때 실제로 그렇게 보였다).
// 다시 보일 때 높이를 재측정하고, 남아 있는 전환은 끝으로 보낸다.
function settleMiniPlayer(): void {
    document.querySelector<HTMLElement>(".mini-player")
        ?.getAnimations().forEach((animation) => animation.finish());
}

function onVisibilityChangeForLayout(): void {
    if (document.visibilityState !== "visible") return;
    measureBarHeights();
    settleMiniPlayer();
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
    if (!lastPlayed) return;
    readerLogic.restoreLastSession(lastPlayed);
    // 앱을 처음 열 때는 미니 플레이어가 미끄러져 올라올 이유가 없다 —
    // 이미 듣던 게 있다는 뜻이니 처음부터 제자리에 있어야 한다. 게다가 첫
    // 화면을 그리는 도중 시작된 전환은 끝까지 진행되지 않고 반쯤 올라온
    // 채로 굳는 일이 있었다(최초 진입에서만 재현됐다). 전환을 바로 끝내
    // 제자리에 놓으면 그 경우가 아예 생기지 않는다.
    requestAnimationFrame(settleMiniPlayer);
}

onMounted(async () => {
    document.addEventListener("keydown", onEscape);
    watchBarHeights();
    document.addEventListener("visibilitychange", onVisibilityChangeForLayout);
    await voiceLogic.loadVoices();
    readerLogic.checkSharedLink();
    restoreLastPlayedSession();
});
</script>

<template>
    <HeaderView :theme-logic="themeLogic" :active-tab="activeTab" />
    <main class="app-main" id="appMain" :class="{ 'has-mini-player': hasMiniPlayer }" v-show="activeTab === 'home'">
        <OnboardingView :state="audioListState" :logic="audioListLogic" />
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

    <LibraryView v-show="activeTab === 'library'" :active="activeTab === 'library'" :logic="readerLogic" :has-mini-player="hasMiniPlayer" :reader-open="readerState.isOpen.value" />

    <MyFilesView
        v-show="activeTab === 'files'"
        :active="activeTab === 'files'"
        :audio-list-state="audioListState"
        :audio-list-logic="audioListLogic"
        :my-files-state="myFilesState"
        :my-files-logic="myFilesLogic"
        :generation-logic="generationLogic"
        :generating-items="generationState.generatingItems.value"
        :has-mini-player="hasMiniPlayer"
        :reader-logic="readerLogic"
    />

    <ProfileView
        :active="activeTab === 'profile'"
        :theme-state="themeState"
        :theme-logic="themeLogic"
        :controls-state="readerControlsState"
        :controls-logic="readerControlsLogic"
        :has-mini-player="hasMiniPlayer"
    />

    <!-- ⚠️ 미니 플레이어는 탭바 위에 "얹히는" 게 아니라 같은 스택에 함께 있다.
         예전에는 탭바 높이를 JS로 재서 --tab-bar-h에 넣고 미니 플레이어의
         bottom으로 썼는데, 탭바에는 padding-bottom: env(safe-area-inset-bottom)이
         있어(아이폰에서 ~34px) 그 값이 safe-area 반영 전에 굳으면 미니 플레이어가
         그만큼 아래로 내려앉았다. 탭바가 z-index로 더 위라 잘려 보였고, 그게
         "미니 플레이어가 뜨다 마는" 증상이었다. 스택으로 묶으면 잴 값이 없어져
         이 실패가 아예 불가능해진다. -->
    <div class="bottom-bars">
        <MiniPlayerView :state="readerState" :logic="readerLogic" :audio-list-state="audioListState" />
        <TabBarView :class="{ 'tab-bar-hidden': readerState.isOpen.value }" :active-tab="activeTab" @select="(tab) => (activeTab = tab)" />
    </div>

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
