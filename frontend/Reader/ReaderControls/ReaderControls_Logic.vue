<script lang="ts">
import type { Ref } from "vue";
import type { ReaderControlsState, RepeatMode, ReaderOptionSheetKind, ReaderFontFamily } from "./ReaderControls_State.vue";
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
    openSheet(kind: ReaderOptionSheetKind): void;
    closeSheet(): void;
    selectRepeatMode(mode: RepeatMode): void;
    selectSpeed(value: number): void;
    selectTimerMinutes(minutes: number): void;
    selectFontFamily(value: ReaderFontFamily): void;
    selectFontSize(value: number): void;
    selectLineHeight(value: number): void;
    skipBack(): void;
    skipForward(): void;
    onEnded(): void;
}

export const REPEAT_MODES: RepeatMode[] = ["off", "all", "one"];
export const REPEAT_LABELS: Record<RepeatMode, string> = { off: "반복 안 함", all: "전체 문서 반복", one: "현재 오디오 반복" };
export const SPEED_OPTIONS = [0.75, 1.0, 1.25, 1.5, 2.0];
export const TIMER_OPTIONS_MIN = [0, 15, 30, 60];
export const TIMER_LABELS: Record<number, string> = { 0: "해제", 15: "15분", 30: "30분", 60: "60분" };
export const FONT_FAMILY_OPTIONS: ReaderFontFamily[] = ["serif", "sans"];
export const FONT_FAMILY_LABELS: Record<ReaderFontFamily, string> = { serif: "명조체", sans: "고딕체" };
export const FONT_SIZE_OPTIONS = [0.9, 1.0, 1.15, 1.3, 1.5];
export const FONT_SIZE_LABELS: Record<number, string> = { 0.9: "작게", 1.0: "보통", 1.15: "크게", 1.3: "매우 크게", 1.5: "최대" };
export const LINE_HEIGHT_OPTIONS = [1.7, 2.0, 2.3];
export const LINE_HEIGHT_LABELS: Record<number, string> = { 1.7: "좁게", 2.0: "보통", 2.3: "넓게" };

// static/js/reader-controls.js를 옮긴 것. 원본은 아이콘을 탭할 때마다
// 다음 값으로 순환했는데, 이번에 시트를 열어 옵션을 직접 선택하는
// 방식으로 바꿨다(사용자 요청 — Speechify 참고). localStorage 키 이름
// ("textAudio_repeatMode", "textAudio_playbackSpeed")은 기존 사용자의
// 설정을 그대로 이어받아야 하므로 동일하게 유지한다.
export function useReaderControlsLogic(state: ReaderControlsState, audioEl: Ref<HTMLAudioElement | null>): ReaderControlsLogic {
    const { showToast } = useToastLogic(useToastState());
    let timerInterval: ReturnType<typeof setInterval> | null = null;
    let timeRemaining = 0;

    const savedRepeat = localStorage.getItem("textAudio_repeatMode") as RepeatMode | null;
    if (savedRepeat && REPEAT_MODES.includes(savedRepeat)) state.repeatMode.value = savedRepeat;
    const savedSpeed = Number.parseFloat(localStorage.getItem("textAudio_playbackSpeed") || "");
    if (SPEED_OPTIONS.includes(savedSpeed)) state.playbackSpeed.value = savedSpeed;
    const savedFontFamily = localStorage.getItem("textAudio_readerFontFamily") as ReaderFontFamily | null;
    if (savedFontFamily && FONT_FAMILY_OPTIONS.includes(savedFontFamily)) state.fontFamily.value = savedFontFamily;
    const savedFontSize = Number.parseFloat(localStorage.getItem("textAudio_readerFontSize") || "");
    if (FONT_SIZE_OPTIONS.includes(savedFontSize)) state.fontSize.value = savedFontSize;
    const savedLineHeight = Number.parseFloat(localStorage.getItem("textAudio_readerLineHeight") || "");
    if (LINE_HEIGHT_OPTIONS.includes(savedLineHeight)) state.lineHeight.value = savedLineHeight;

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
        state.timerLabel.value = "사용 안 함";
    }

    function updateTimerDisplay(): void {
        if (timeRemaining <= 0) return;
        const minutes = Math.floor(timeRemaining / 60);
        const seconds = timeRemaining % 60;
        state.timerLabel.value = `${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
    }

    function openSheet(kind: ReaderOptionSheetKind): void {
        state.activeSheet.value = kind;
    }

    function closeSheet(): void {
        state.activeSheet.value = null;
    }

    function selectRepeatMode(mode: RepeatMode): void {
        state.repeatMode.value = mode;
        localStorage.setItem("textAudio_repeatMode", mode);
        showToast(`반복 모드: ${REPEAT_LABELS[mode]}`, "info");
        closeSheet();
    }

    function selectSpeed(value: number): void {
        state.playbackSpeed.value = value;
        if (audioEl.value) audioEl.value.playbackRate = value;
        localStorage.setItem("textAudio_playbackSpeed", String(value));
        showToast(`재생 속도 ${value}x`, "info");
        closeSheet();
    }

    function selectTimerMinutes(minutes: number): void {
        if (timerInterval) clearInterval(timerInterval);

        if (minutes === 0) {
            clearSleepTimer();
            showToast("취침 타이머가 해제되었습니다.", "info");
            closeSheet();
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
        closeSheet();
    }

    function selectFontFamily(value: ReaderFontFamily): void {
        state.fontFamily.value = value;
        localStorage.setItem("textAudio_readerFontFamily", value);
        showToast(`글꼴: ${FONT_FAMILY_LABELS[value]}`, "info");
        closeSheet();
    }

    function selectFontSize(value: number): void {
        state.fontSize.value = value;
        localStorage.setItem("textAudio_readerFontSize", String(value));
        showToast(`글자 크기: ${FONT_SIZE_LABELS[value]}`, "info");
        closeSheet();
    }

    function selectLineHeight(value: number): void {
        state.lineHeight.value = value;
        localStorage.setItem("textAudio_readerLineHeight", String(value));
        showToast(`줄 간격: ${LINE_HEIGHT_LABELS[value]}`, "info");
        closeSheet();
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
        openSheet, closeSheet, selectRepeatMode, selectSpeed, selectTimerMinutes,
        selectFontFamily, selectFontSize, selectLineHeight,
        skipBack, skipForward, onEnded,
    };
}

export default {};
</script>
