<script lang="ts">
import { ref, type Ref } from "vue";

export interface LibraryUploadSheetState {
    isOpen: Ref<boolean>;
    text: Ref<string>;
    status: Ref<string>;
    submitting: Ref<boolean>;
}

const state: LibraryUploadSheetState = {
    isOpen: ref(false),
    text: ref(""),
    status: ref(""),
    submitting: ref(false),
};

export function useLibraryUploadSheetState(): LibraryUploadSheetState {
    return state;
}

export default {};
</script>
