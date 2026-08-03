<script lang="ts">
import type { VoiceOption, VoiceState } from "./Voice_State.vue";
import { useToastLogic } from "../components/Toast/Toast_Logic.vue";
import { useToastState } from "../components/Toast/Toast_State.vue";

export interface VoiceLogic {
    loadVoices(): Promise<void>;
    updateDescription(voiceKey: string): void;
    togglePreview(): Promise<void>;
    stopPreview(): void;
    getSelectedVoice(): string;
}

// 백엔드 tts_providers/voice_catalog.py의 VOICE_CATALOG과 같은 목록이어야
// 한다 — 여기 있는데 백엔드엔 없는(혹은 그 반대인) 음성은 선택은 되지만
// 합성 시 알 수 없는 값이라 기본 음성으로 조용히 대체된다.
const FALLBACK_VOICES: VoiceOption[] = [
    { key: "ko_male_warm", friendly_name: "🇰🇷 현수 (자연스러운 낭독 - 남성)", locale: "ko-KR", description: "억양이 자연스럽고, 한글과 영어가 섞인 문장도 매끄럽게 읽습니다." },
    { key: "ko_female_calm", friendly_name: "🇰🇷 선희 (차분한 낭독 - 여성)", locale: "ko-KR", description: "단정하고 차분한 여성 음성으로, 정보 전달이나 긴 호흡의 낭독에 적합합니다." },
];

export function useVoiceLogic(state: VoiceState): VoiceLogic {
    const { showToast } = useToastLogic(useToastState());
    let previewAudio: HTMLAudioElement | null = null;

    function updateDescription(voiceKey: string): void {
        const voice = state.voices.value.find((item) => item.key === voiceKey);
        state.voiceDesc.value = voice?.description || "선택한 음성의 상세 특징이 표시됩니다.";
    }

    function stopPreview(): void {
        if (previewAudio) {
            previewAudio.pause();
            previewAudio = null;
        }
        state.isPreviewBusy.value = false;
        state.previewLabel.value = "미리듣기";
    }

    async function togglePreview(): Promise<void> {
        if (previewAudio) {
            stopPreview();
            return;
        }
        const voice = state.selectedVoice.value;
        if (!voice) return;

        state.isPreviewBusy.value = true;
        state.previewLabel.value = "준비 중...";
        try {
            const response = await fetch(`/api/voices/${encodeURIComponent(voice)}/preview`);
            if (!response.ok) throw new Error("미리듣기를 불러오지 못했습니다.");
            const blob = await response.blob();

            previewAudio = new Audio(URL.createObjectURL(blob));
            previewAudio.onended = stopPreview;
            previewAudio.onerror = () => {
                stopPreview();
                showToast("미리듣기를 재생하지 못했습니다.", "error");
            };
            state.isPreviewBusy.value = false;
            state.previewLabel.value = "정지";
            await previewAudio.play();
        } catch (error) {
            console.error(error);
            stopPreview();
            showToast((error as Error).message || "미리듣기에 실패했습니다.", "error");
        }
    }

    async function loadVoices(): Promise<void> {
        try {
            const response = await fetch("/api/voices");
            if (!response.ok) throw new Error("목소리 목록을 불러오지 못했습니다.");
            const voices: VoiceOption[] = await response.json();

            if (voices.length === 0) {
                state.voices.value = FALLBACK_VOICES;
            } else {
                state.voices.value = voices.map((voice) => ({
                    ...voice,
                    friendly_name: `${voice.locale.startsWith("ko-KR") ? "🇰🇷" : "🇺🇸"} ${voice.friendly_name}`,
                }));
            }
            state.selectedVoice.value = state.voices.value[0].key;
            updateDescription(state.selectedVoice.value);
        } catch (error) {
            console.error(error);
            showToast("음성 목록을 가져오지 못했습니다. 기본 설정을 사용합니다.", "error");
            state.voices.value = FALLBACK_VOICES;
            state.selectedVoice.value = FALLBACK_VOICES[0].key;
            updateDescription(state.selectedVoice.value);
        }
    }

    return {
        loadVoices,
        updateDescription,
        togglePreview,
        stopPreview,
        getSelectedVoice: () => state.selectedVoice.value,
    };
}

export default {};
</script>
