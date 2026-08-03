<script setup lang="ts">
import { ref, watch } from "vue";
import type { MyFilesState } from "../Files/MyFiles_State.vue";
import type { MyFilesLogic } from "../Files/MyFiles_Logic.vue";
import { useSwipeToDismiss } from "../utils/swipeToDismiss";

const props = defineProps<{
    state: MyFilesState;
    logic: MyFilesLogic;
    onAddFolder: () => void;
    onAddFile: () => void;
}>();

const sheet = ref<HTMLElement | null>(null);
useSwipeToDismiss(sheet, () => props.logic.closeAddMenu());

watch(() => props.state.isAddMenuOpen.value, (open) => {
    document.body.style.overflow = open ? "hidden" : "";
});

function onBackdropClick(event: MouseEvent): void {
    if (event.target === event.currentTarget) props.logic.closeAddMenu();
}

function onAddFolderClick(): void {
    props.logic.closeAddMenu();
    props.onAddFolder();
}

function onAddFileClick(): void {
    props.logic.closeAddMenu();
    props.onAddFile();
}
</script>

<template>
    <div
        class="action-sheet-backdrop"
        :class="{ show: state.isAddMenuOpen.value }"
        role="dialog"
        aria-modal="true"
        aria-label="추가"
        @click="onBackdropClick"
    >
        <div class="action-sheet" ref="sheet">
            <div class="action-sheet-handle"></div>
            <button class="action-sheet-btn" type="button" @click="onAddFolderClick">
                <i data-lucide="folder-plus"></i>
                폴더 추가
            </button>
            <button class="action-sheet-btn" type="button" @click="onAddFileClick">
                <i data-lucide="file-plus"></i>
                파일 추가
            </button>
            <button class="action-sheet-btn action-sheet-btn-cancel" type="button" @click="logic.closeAddMenu">닫기</button>
        </div>
    </div>
</template>
