<script lang="ts">
import type { Ref } from "vue";
import type { ReaderControlsState, RepeatMode } from "./ReaderControls_State.vue";
import { useToastLogic } from "../../components/Toast/Toast_Logic.vue";
import { useToastState } from "../../components/Toast/Toast_State.vue";

export interface PlaybackSettings {
    playbackSpeed: number;
    repeatMode: RepeatMode;
}

export interface ReaderControlsLogic {
    getPlaybackSettings(): PlaybackSettings;
    applyPlaybackSettings(settings: { playbackSpeed?: number; repeatMode?: string }): void;
    clearSleepTimer(): void;
    toggleRepeat(): void;
    cycleSpeed(): void;
    cycleTimer(): void;
    skipBack(): void;
    skipForward(): void;
    onEnded(): void;
}

const REPEAT_MODES: RepeatMode[] = ["off", "all", "one"];
const REPEAT_LABELS: Record<RepeatMode, string> = { off: "반복 안 함", all: "전체 반복", one: "한 곡 반복" };
const SPEED_OPTIONS = [0.75, 1.0, 1.25, 1.5, 2.0];
const TIMER_OPTIONS_MIN = [0, 15, 30, 60];

// static/js/reader-controls.js를 옮긴 것. localStorage에 저장하는 키
// 이름("textAudio_repeatMode", "textAudio_playbackSpeed")은 기존 사용자의
// 설정을 그대로 이어받아야 하므로 동일하게 유지한다.
export function useReaderControlsLogic(state: ReaderControlsState, audioEl: Ref<HTMLAudioElement | null>): ReaderControlsLogic {
    const { showToast } = useToastLogic(useToastState());
    let timerInterval: ReturnType<typeof setInterval> | null = null;
    let timerIndex = 0;
    let timeRemaining = 0;

    const savedRepeat = localStorage.getItem("textAudio_repeatMode") as RepeatMode | null;
    if (savedRepeat && REPEAT_MODES.includes(savedRepeat)) state.repeatMode.value = savedRepeat;
    const savedSpeed = Number.parseFloat(localStorage.getItem("textAudio_playbackSpeed") || "");
    if (SPEED_OPTIONS.includes(savedSpeed)) state.playbackSpeed.value = savedSpeed;

    function getPlaybackSettings(): PlaybackSettings {
        return { playbackSpeed: state.playbackSpeed.value, repeatMode: state.repeatMode.value };
    }

    function applyPlaybackSettings({ playbackSpeed, repeatMode }: { playbackSpeed?: number; repeatMode?: string } = {}): void {
        if (playbackSpeed !== undefined && SPEED_OPTIONS.includes(Number(playbackSpeed))) state.playbackSpeed.value = Number(playbackSpeed);
        if (repeatMode !== undefined && REPEAT_MODES.includes(repeatMode as RepeatMode)) state.repeatMode.value = repeatMode as RepeatMode;
        if (audioEl.value) audioEl.value.playbackRate = state.playbackSpeed.value;
    }

    function clearSleepTimer(): void {
        if (timerInterval) clearInterval(timerInterval);
        timerInterval = null;
        state.isTimerActive.value = false;
        state.timerLabel.value = "타이머";
        timerIndex = 0;
    }

    function updateTimerDisplay(): void {
        if (timeRemaining <= 0) return;
        const minutes = Math.floor(timeRemaining / 60);
        const seconds = timeRemaining % 60;
        state.timerLabel.value = `${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
    }

    function toggleRepeat(): void {
        const index = (REPEAT_MODES.indexOf(state.repeatMode.value) + 1) % REPEAT_MODES.length;
        state.repeatMode.value = REPEAT_MODES[index];
        localStorage.setItem("textAudio_repeatMode", state.repeatMode.value);
        showToast(`반복 모드: ${REPEAT_LABELS[state.repeatMode.value]}`, "info");
    }

    function cycleSpeed(): void {
        const index = (SPEED_OPTIONS.indexOf(state.playbackSpeed.value) + 1) % SPEED_OPTIONS.length;
        state.playbackSpeed.value = SPEED_OPTIONS[index];
        if (audioEl.value) audioEl.value.playbackRate = state.playbackSpeed.value;
        localStorage.setItem("textAudio_playbackSpeed", String(state.playbackSpeed.value));
        showToast(`재생 속도 ${state.playbackSpeed.value}x`, "info");
    }

    function cycleTimer(): void {
        timerIndex = (timerIndex + 1) % TIMER_OPTIONS_MIN.length;
        const minutes = TIMER_OPTIONS_MIN[timerIndex];
        if (timerInterval) clearInterval(timerInterval);

        if (minutes === 0) {
            clearSleepTimer();
            showToast("취침 타이머가 해제되었습니다.", "info");
            return;
        }

        state.isTimerActive.value = true;
        timeRemaining = minutes * 60;
        updateTimerDisplay();
        timerInterval = setInterval(() => {
            timeRemaining -= 1;
            if (timeRemaining <= 0) {
                audioEl.value?.pause();
                clearSleepTimer();
                showToast("타이머가 종료되어 재생을 멈췄습니다.", "info");
            } else {
                updateTimerDisplay();
            }
        }, 1000);
        showToast(`${minutes}분 뒤에 재생이 자동 종료됩니다.`, "info");
    }

    function skipBack(): void {
        if (audioEl.value && !Number.isNaN(audioEl.value.currentTime)) {
            audioEl.value.currentTime = Math.max(0, audioEl.value.currentTime - 10);
        }
    }

    function skipForward(): void {
        if (audioEl.value && !Number.isNaN(audioEl.value.duration)) {
            audioEl.value.currentTime = Math.min(audioEl.value.duration, audioEl.value.currentTime + 10);
        }
    }

    function onEnded(): void {
        if (state.repeatMode.value === "all" || state.repeatMode.value === "one") {
            if (audioEl.value) {
                audioEl.value.currentTime = 0;
                audioEl.value.play().catch((error) => console.log("Autoplay blocked:", error));
            }
        }
    }

    return {
        getPlaybackSettings, applyPlaybackSettings, clearSleepTimer,
        toggleRepeat, cycleSpeed, cycleTimer, skipBack, skipForward, onEnded,
    };
}

export default {};
</script>
