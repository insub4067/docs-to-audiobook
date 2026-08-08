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
        // 기본값은 "전체 문서 반복"이다. 이 앱은 문서 하나를 끝까지 듣고
        // 마는 것보다, 틀어 놓고 이어 듣는 쓰임이 많다(경제 뉴스 연속 듣기,
        // 경전 정주행). 껐다 켤 때마다 다시 켜야 하는 쪽이 번거롭다.
        repeatMode: ref("all"),
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
