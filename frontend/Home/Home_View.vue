<script setup lang="ts">
import { onMounted } from "vue";
import HeaderView from "../components/Header/Header_View.vue";
import UploadView from "../components/Upload/Upload_View.vue";
import GenerationModalView from "../Sheet/GenerationModal_View.vue";
import LoginPromptSheetView from "../Sheet/LoginPromptSheet_View.vue";
import AudioListView from "../components/Library/AudioList_View.vue";
import ReaderView from "../Reader/Reader_View.vue";
import { useGenerationState } from "../Generation/Generation_State.vue";
import { useGenerationLogic } from "../Generation/Generation_Logic.vue";
import { useVoiceState } from "../Voices/Voice_State.vue";
import { useVoiceLogic } from "../Voices/Voice_Logic.vue";
import { useAudioListState } from "../components/Library/AudioList_State.vue";
import { useAudioListLogic } from "../components/Library/AudioList_Logic.vue";
import { useReaderState } from "../Reader/Reader_State.vue";
import { useReaderLogic } from "../Reader/Reader_Logic.vue";
import { useReaderControlsState } from "../Reader/ReaderControls/ReaderControls_State.vue";
import { useReaderControlsLogic } from "../Reader/ReaderControls/ReaderControls_Logic.vue";
import { usePwaState } from "../components/Pwa/Pwa_State.vue";

const pwaState = usePwaState();
const voiceState = useVoiceState();
const voiceLogic = useVoiceLogic(voiceState);
const generationState = useGenerationState();
const generationLogic = useGenerationLogic(generationState, voiceLogic);
const audioListState = useAudioListState();
const audioListLogic = useAudioListLogic(audioListState);

const readerState = useReaderState();
const readerControlsState = useReaderControlsState();
const readerControlsLogic = useReaderControlsLogic(readerControlsState, readerState.audioEl);
const readerLogic = useReaderLogic(readerState, readerControlsLogic, audioListLogic);

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
    <HeaderView />
    <main class="app-main" id="appMain">
        <UploadView :state="generationState" :logic="generationLogic" />
        <AudioListView
            :state="audioListState"
            :logic="audioListLogic"
            :generating-items="generationState.generatingItems.value"
            :on-import-link="onImportLink"
        />
    </main>
    <footer class="app-version-footer">
        <span>{{ pwaState.versionLabel.value }}</span>
    </footer>

    <GenerationModalView :state="generationState" :logic="generationLogic" :voice-state="voiceState" :voice-logic="voiceLogic" />
    <LoginPromptSheetView :state="generationState" :logic="generationLogic" />
    <ReaderView
        :state="readerState"
        :logic="readerLogic"
        :controls-state="readerControlsState"
        :controls-logic="readerControlsLogic"
        :audio-list-logic="audioListLogic"
    />
</template>
