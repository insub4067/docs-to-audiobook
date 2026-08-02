<script lang="ts">
import { getAllAudiobooksFromDB } from "../../services/indexedDb";
import type { AudioListState } from "./AudioList_State.vue";

export interface AudioListLogic {
    refresh(): Promise<void>;
}

// static/js/library.js의 render()를 옮긴 것 — 지금은 목록 조회/표시까지만
// 담당한다. 스와이프 삭제, 액션시트(공유/다운로드/제목수정/삭제), 클라우드
// 동기화, 리더 열기는 Library 기능을 본격적으로 포팅하는 다음 단계에서
// 이 파일에 이어 붙인다.
export function useAudioListLogic(state: AudioListState): AudioListLogic {
    async function refresh(): Promise<void> {
        try {
            state.savedAudiobooks.value = await getAllAudiobooksFromDB();
        } catch (error) {
            console.error("Library render error: ", error);
        }
    }

    (window as any).__renderLibrary = refresh;

    return { refresh };
}

export default {};
</script>
