<script lang="ts">
import { ref, type Ref } from "vue";
import type { AudiobookRecord } from "../../services/indexedDb";

export interface AudioListState {
    savedAudiobooks: Ref<AudiobookRecord[]>;
    actionSheetTarget: Ref<AudiobookRecord | null>;
    isActionSheetOpen: Ref<boolean>;
}

export function useAudioListState(): AudioListState {
    return {
        savedAudiobooks: ref([]),
        actionSheetTarget: ref(null),
        isActionSheetOpen: ref(false),
    };
}

export default {};
</script>
