<script lang="ts">
import { ref, type Ref } from "vue";

export type RepeatMode = "off" | "all" | "one" | "chapter";
export type ReaderFontFamily = "serif" | "sans";
export type ReaderOptionSheetKind = "repeat" | "speed" | "timer" | "fontFamily" | "fontSize" | "lineHeight" | null;

export interface ReaderControlsState {
    repeatMode: Ref<RepeatMode>;
    /** 지금 듣는 장이 끝나면 멈춘다. 취침 타이머의 장 단위 버전이다. */
    stopAtChapterEnd: Ref<boolean>;
    playbackSpeed: Ref<number>;
    timerLabel: Ref<string>;
    isTimerActive: Ref<boolean>;
    activeSheet: Ref<ReaderOptionSheetKind>;
    fontFamily: Ref<ReaderFontFamily>;
    fontSize: Ref<number>;
    lineHeight: Ref<number>;
}

export function useReaderControlsState(): ReaderControlsState {
    return {
        repeatMode: ref("off"),
        stopAtChapterEnd: ref(false),
        playbackSpeed: ref(1.0),
        timerLabel: ref("사용 안 함"),
        isTimerActive: ref(false),
        activeSheet: ref(null),
        fontFamily: ref("serif"),
        fontSize: ref(1.0),
        lineHeight: ref(2.0),
    };
}

export default {};
</script>
