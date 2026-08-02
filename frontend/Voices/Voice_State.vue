<script lang="ts">
import { ref, type Ref } from "vue";

export interface VoiceOption {
    short_name: string;
    friendly_name: string;
    locale: string;
    description?: string;
}

export interface VoiceState {
    voices: Ref<VoiceOption[]>;
    selectedVoice: Ref<string>;
    voiceDesc: Ref<string>;
    isPreviewBusy: Ref<boolean>;
    previewLabel: Ref<string>;
}

export function useVoiceState(): VoiceState {
    return {
        voices: ref([]),
        selectedVoice: ref(""),
        voiceDesc: ref("선택한 음성의 상세 특징이 표시됩니다."),
        isPreviewBusy: ref(false),
        previewLabel: ref("미리듣기"),
    };
}

export default {};
</script>
