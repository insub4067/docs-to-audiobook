<script lang="ts">
import { ref, type Ref } from "vue";
import type { AudiobookRecord } from "../services/indexedDb";
import type { FolderNode } from "./FolderBrowser_State.vue";

export interface MyFilesState {
    isFolderActionSheetOpen: Ref<boolean>;
    folderActionTarget: Ref<FolderNode | null>;
    isMovePickerOpen: Ref<boolean>;
    moveTarget: Ref<AudiobookRecord | null>;
    isAddMenuOpen: Ref<boolean>;
}

export function useMyFilesState(): MyFilesState {
    return {
        isFolderActionSheetOpen: ref(false),
        folderActionTarget: ref(null),
        isMovePickerOpen: ref(false),
        moveTarget: ref(null),
        isAddMenuOpen: ref(false),
    };
}

export default {};
</script>
