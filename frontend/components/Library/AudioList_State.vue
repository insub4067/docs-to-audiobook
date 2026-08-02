<script lang="ts">
import { ref, type Ref } from "vue";
import type { AudiobookRecord } from "../../services/indexedDb";

export interface AudioListState {
    savedAudiobooks: Ref<AudiobookRecord[]>;
}

export function useAudioListState(): AudioListState {
    return {
        savedAudiobooks: ref([]),
    };
}

export default {};
</script>
