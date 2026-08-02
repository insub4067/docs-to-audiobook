<script setup lang="ts">
import { onMounted } from "vue";
import HeaderView from "../components/AppHeader/Header_View.vue";
import UploadView from "../components/Upload/Upload_View.vue";
import GenerationModalView from "../components/Upload/GenerationModal_View.vue";
import LoginPromptSheetView from "../components/Upload/LoginPromptSheet_View.vue";
import AudioListView from "../components/Library/AudioList_View.vue";
import { useGenerationState } from "../composables/Generation/Generation_State.vue";
import { useGenerationLogic } from "../composables/Generation/Generation_Logic.vue";
import { useVoiceState } from "../composables/Voices/Voice_State.vue";
import { useVoiceLogic } from "../composables/Voices/Voice_Logic.vue";
import { useAudioListState } from "../components/Library/AudioList_State.vue";
import { useAudioListLogic } from "../components/Library/AudioList_Logic.vue";

const voiceState = useVoiceState();
const voiceLogic = useVoiceLogic(voiceState);
const generationState = useGenerationState();
const generationLogic = useGenerationLogic(generationState, voiceLogic);
const audioListState = useAudioListState();
const audioListLogic = useAudioListLogic(audioListState);

function onEscape(event: KeyboardEvent): void {
    if (event.key !== "Escape") return;
    if (generationState.isLoginPromptOpen.value) generationState.isLoginPromptOpen.value = false;
    else if (generationState.isModalOpen.value) generationLogic.closeModal();
}

onMounted(async () => {
    document.addEventListener("keydown", onEscape);
    await voiceLogic.loadVoices();
});
</script>

<template>
    <HeaderView />
    <main class="app-main" id="appMain">
        <UploadView :state="generationState" :logic="generationLogic" />
        <AudioListView :state="audioListState" :logic="audioListLogic" :generating-items="generationState.generatingItems.value" />
    </main>
    <footer class="app-version-footer">
        <span>v --</span>
    </footer>

    <GenerationModalView :state="generationState" :logic="generationLogic" :voice-state="voiceState" :voice-logic="voiceLogic" />
    <LoginPromptSheetView :state="generationState" :logic="generationLogic" />
</template>
