<script lang="ts">
import type { VoiceOption, VoiceState } from "./Voice_State.vue";
import { useToastLogic } from "../components/Toast/Toast_Logic.vue";
import { useToastState } from "../components/Toast/Toast_State.vue";

export interface VoiceLogic {
    loadVoices(): Promise<void>;
    updateDescription(shortName: string): void;
    togglePreview(): Promise<void>;
    stopPreview(): void;
    getSelectedVoice(): string;
}

const FALLBACK_VOICES: VoiceOption[] = [
    { short_name: "ko-KR-SunHiNeural", friendly_name: "🇰🇷 선희 (차분한 뉴스/정보 전달 - 여성)", locale: "ko-KR", description: "단정하고 차분하며, 정보 전달이나 지적인 낭독에 적합합니다." },
    { short_name: "ko-KR-InJoonNeural", friendly_name: "🇰🇷 인준 (신뢰감 있는 소설/다큐 - 남성)", locale: "ko-KR", description: "진중하고 신뢰감 있는 남성 톤으로, 다큐멘터리나 소설 낭독에 적합합니다." },
    { short_name: "ko-KR-JiMinNeural", friendly_name: "🇰🇷 지민 (밝고 상냥한 동화/안내 - 여성)", locale: "ko-KR", description: "밝고 친근하며, 동화책 낭독이나 상냥한 안내 멘트에 잘 어울립니다." },
];

export function useVoiceLogic(state: VoiceState): VoiceLogic {
    const { showToast } = useToastLogic(useToastState());
    let previewAudio: HTMLAudioElement | null = null;

    function updateDescription(shortName: string): void {
        const voice = state.voices.value.find((item) => item.short_name === shortName);
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
                state.voices.value = [{ short_name: "ko-KR-SunHiNeural", friendly_name: "선희 (차분한 뉴스/정보 전달 - 여성)", locale: "ko-KR" }];
            } else {
                state.voices.value = voices.map((voice) => ({
                    ...voice,
                    friendly_name: `${voice.locale.startsWith("ko-KR") ? "🇰🇷" : "🇺🇸"} ${voice.friendly_name}`,
                }));
            }
            state.selectedVoice.value = state.voices.value[0].short_name;
            updateDescription(state.selectedVoice.value);
        } catch (error) {
            console.error(error);
            showToast("음성 목록을 가져오지 못했습니다. 기본 설정을 사용합니다.", "error");
            state.voices.value = FALLBACK_VOICES;
            state.selectedVoice.value = FALLBACK_VOICES[0].short_name;
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
