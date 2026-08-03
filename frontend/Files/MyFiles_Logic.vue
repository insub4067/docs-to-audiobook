<script lang="ts">
import type { MyFilesState } from "./MyFiles_State.vue";
import type { FolderNode } from "./FolderBrowser_State.vue";
import type { AudiobookRecord } from "../services/indexedDb";

export interface MyFilesLogic {
    openFolderActionSheet(folder: FolderNode): void;
    closeFolderActionSheet(): void;
    openMovePicker(audio: AudiobookRecord): void;
    closeMovePicker(): void;
    openAddMenu(): void;
    closeAddMenu(): void;
}

export function useMyFilesLogic(state: MyFilesState): MyFilesLogic {
    function openFolderActionSheet(folder: FolderNode): void {
        state.folderActionTarget.value = folder;
        state.isFolderActionSheetOpen.value = true;
    }

    function closeFolderActionSheet(): void {
        state.isFolderActionSheetOpen.value = false;
        state.folderActionTarget.value = null;
    }

    function openMovePicker(audio: AudiobookRecord): void {
        state.moveTarget.value = audio;
        state.isMovePickerOpen.value = true;
    }

    function closeMovePicker(): void {
        state.isMovePickerOpen.value = false;
        state.moveTarget.value = null;
    }

    function openAddMenu(): void {
        state.isAddMenuOpen.value = true;
    }

    function closeAddMenu(): void {
        state.isAddMenuOpen.value = false;
    }

    return {
        openFolderActionSheet, closeFolderActionSheet, openMovePicker, closeMovePicker,
        openAddMenu, closeAddMenu,
    };
}

export default {};
</script>
