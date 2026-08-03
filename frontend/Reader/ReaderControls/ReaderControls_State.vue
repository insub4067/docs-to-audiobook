<script lang="ts">
import { ref, type Ref } from "vue";

export type RepeatMode = "off" | "all" | "one";
export type ReaderFontFamily = "serif" | "sans";
export type ReaderOptionSheetKind = "repeat" | "speed" | "timer" | "fontFamily" | "fontSize" | null;

export interface ReaderControlsState {
    repeatMode: Ref<RepeatMode>;
    playbackSpeed: Ref<number>;
    timerLabel: Ref<string>;
    isTimerActive: Ref<boolean>;
    activeSheet: Ref<ReaderOptionSheetKind>;
    fontFamily: Ref<ReaderFontFamily>;
    fontSize: Ref<number>;
}

export function useReaderControlsState(): ReaderControlsState {
    return {
        repeatMode: ref("off"),
        playbackSpeed: ref(1.0),
        timerLabel: ref("타이머"),
        isTimerActive: ref(false),
        activeSheet: ref(null),
        fontFamily: ref("serif"),
        fontSize: ref(1.0),
    };
}

export default {};
</script>
