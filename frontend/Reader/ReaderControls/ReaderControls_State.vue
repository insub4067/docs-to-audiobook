<script lang="ts">
import { ref, type Ref } from "vue";

export type RepeatMode = "off" | "all" | "one";
export type ReaderOptionSheetKind = "repeat" | "speed" | "timer" | null;

export interface ReaderControlsState {
    repeatMode: Ref<RepeatMode>;
    playbackSpeed: Ref<number>;
    timerLabel: Ref<string>;
    isTimerActive: Ref<boolean>;
    activeSheet: Ref<ReaderOptionSheetKind>;
}

export function useReaderControlsState(): ReaderControlsState {
    return {
        repeatMode: ref("off"),
        playbackSpeed: ref(1.0),
        timerLabel: ref("타이머"),
        isTimerActive: ref(false),
        activeSheet: ref(null),
    };
}

export default {};
</script>
