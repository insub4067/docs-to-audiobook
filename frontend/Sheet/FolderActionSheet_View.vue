<script setup lang="ts">
import { ref, watch } from "vue";
import type { MyFilesState } from "../Files/MyFiles_State.vue";
import type { MyFilesLogic } from "../Files/MyFiles_Logic.vue";
import type { FolderBrowserLogic } from "../Files/FolderBrowser_Logic.vue";
import { useSwipeToDismiss } from "../utils/swipeToDismiss";
import { usePromptSheetLogic } from "./PromptSheet_Logic.vue";
import { usePromptSheetState } from "./PromptSheet_State.vue";

const props = defineProps<{
    state: MyFilesState;
    logic: MyFilesLogic;
    folderBrowserLogic: FolderBrowserLogic;
}>();

const promptSheetLogic = usePromptSheetLogic(usePromptSheetState());

const sheet = ref<HTMLElement | null>(null);
useSwipeToDismiss(sheet, () => props.logic.closeFolderActionSheet());

watch(() => props.state.isFolderActionSheetOpen.value, (open) => {
    document.body.style.overflow = open ? "hidden" : "";
});

function onBackdropClick(event: MouseEvent): void {
    if (event.target === event.currentTarget) props.logic.closeFolderActionSheet();
}

async function onRename(): Promise<void> {
    const target = props.state.folderActionTarget.value;
    if (!target) return;
    props.logic.closeFolderActionSheet();
    const name = await promptSheetLogic.showPrompt("폴더 이름", { defaultValue: target.name });
    if (name === null) return;
    await props.folderBrowserLogic.renameFolder(target, name);
}

async function onDelete(): Promise<void> {
    const target = props.state.folderActionTarget.value;
    if (!target) return;
    props.logic.closeFolderActionSheet();
    if (!window.confirm(`"${target.name}" 폴더를 삭제할까요?\n안의 파일과 하위 폴더는 상위 폴더로 이동합니다.`)) return;
    await props.folderBrowserLogic.deleteFolder(target);
}
</script>

<template>
    <div
        class="action-sheet-backdrop"
        :class="{ show: state.isFolderActionSheetOpen.value }"
        role="dialog"
        aria-modal="true"
        aria-label="폴더 작업"
        @click="onBackdropClick"
    >
        <div class="action-sheet" ref="sheet">
            <div class="action-sheet-handle"></div>
            <button class="action-sheet-btn" type="button" @click="onRename">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"></path><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"></path></svg>
                이름 변경
            </button>
            <button class="action-sheet-btn action-sheet-btn-danger" type="button" @click="onDelete">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                삭제
            </button>
            <button class="action-sheet-btn action-sheet-btn-cancel" type="button" @click="logic.closeFolderActionSheet">닫기</button>
        </div>
    </div>
</template>
