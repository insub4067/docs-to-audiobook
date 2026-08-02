<script lang="ts">
import { ref, type Ref } from "vue";

export type RepeatMode = "off" | "all" | "one";

export interface ReaderControlsState {
    repeatMode: Ref<RepeatMode>;
    playbackSpeed: Ref<number>;
    timerLabel: Ref<string>;
    isTimerActive: Ref<boolean>;
}

export function useReaderControlsState(): ReaderControlsState {
    return {
        repeatMode: ref("off"),
        playbackSpeed: ref(1.0),
        timerLabel: ref("타이머"),
        isTimerActive: ref(false),
    };
}

export default {};
</script>
