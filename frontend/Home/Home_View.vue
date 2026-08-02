<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import HeaderView from "../components/Header/Header_View.vue";
import UploadView from "../components/Upload/Upload_View.vue";
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

// 홈 화면 "내 오디오북"은 최대 5개만 — 북마크된 항목을 먼저 채우고,
// 나머지는 추가되거나 재생된 시각 중 더 최근인 순으로 채운다.
const HOME_SUMMARY_LIMIT = 5;
function recencyScore(audio: AudiobookRecord): number {
    return Math.max(audio.timestamp || 0, audio.playbackUpdatedAt || 0);
}
const homeSummaryItems = computed(() => {
    const items = audioListState.savedAudiobooks.value;
    const bookmarked = items.filter((a) => a.isBookmarked).sort((a, b) => recencyScore(b) - recencyScore(a));
    const rest = items.filter((a) => !a.isBookmarked).sort((a, b) => recencyScore(b) - recencyScore(a));
    return [...bookmarked, ...rest].slice(0, HOME_SUMMARY_LIMIT);
});

function onEscape(event: KeyboardEvent): void {
    if (event.key !== "Escape") return;
    if (generationState.isLoginPromptOpen.value) generationState.isLoginPromptOpen.value = false;
    else if (readerLogic.closeIndexSheetIfOpen()) {
        // 목차 시트를 닫았다
    } else if (generationState.isModalOpen.value) generationLogic.closeModal();
}

function onImportLink(): void {
    const url = window.prompt("공유받은 링크를 붙여넣어 주세요:\n(예: https://.../share/...)");
    if (url) readerLogic.importSharedLink(url);
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
        <UploadView :state="generationState" :logic="generationLogic" />
        <AudioListView
            :state="audioListState"
            :logic="audioListLogic"
            :my-files-logic="myFilesLogic"
            :items="homeSummaryItems"
            :generating-items="generationState.generatingItems.value"
            :on-import-link="onImportLink"
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
    />

    <TabBarView v-show="!readerState.isOpen.value" :active-tab="activeTab" @select="(tab) => (activeTab = tab)" />

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
