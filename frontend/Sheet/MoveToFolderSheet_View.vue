<script setup lang="ts">
import { ref, watch } from "vue";
import type { MyFilesState } from "../Files/MyFiles_State.vue";
import type { MyFilesLogic } from "../Files/MyFiles_Logic.vue";
import type { AudioListLogic } from "../components/Library/AudioList_Logic.vue";
import { useFolderBrowserState } from "../Files/FolderBrowser_State.vue";
import { useFolderBrowserLogic } from "../Files/FolderBrowser_Logic.vue";
import { useSwipeToDismiss } from "../utils/swipeToDismiss";

const props = defineProps<{
    state: MyFilesState;
    logic: MyFilesLogic;
    audioListLogic: AudioListLogic;
}>();

// 메인 화면 탐색과 별개의 탐색 스택 — 이동 대상을 고르는 동안 뒤에 있는
// 내 파일 화면의 현재 위치는 그대로 유지되어야 한다.
const browserState = useFolderBrowserState("내 파일");
const browserLogic = useFolderBrowserLogic(browserState);

const sheet = ref<HTMLElement | null>(null);
useSwipeToDismiss(sheet, () => props.logic.closeMovePicker());

watch(() => props.state.isMovePickerOpen.value, (open) => {
    document.body.style.overflow = open ? "hidden" : "";
    if (open) {
        browserState.currentFolderId.value = null;
        browserState.breadcrumb.value = [{ id: null, name: "내 파일" }];
        browserLogic.loadCurrentFolder();
    }
});

function onBackdropClick(event: MouseEvent): void {
    if (event.target === event.currentTarget) props.logic.closeMovePicker();
}

async function onConfirmMoveHere(): Promise<void> {
    const target = props.state.moveTarget.value;
    if (!target) return;
    const ok = await props.audioListLogic.moveToFolder(target, browserState.currentFolderId.value);
    if (ok) props.logic.closeMovePicker();
}
</script>

<template>
    <div
        class="action-sheet-backdrop"
        :class="{ show: state.isMovePickerOpen.value }"
        role="dialog"
        aria-modal="true"
        aria-label="폴더로 이동"
        @click="onBackdropClick"
    >
        <div class="action-sheet" ref="sheet">
            <div class="action-sheet-handle"></div>
            <div class="index-sheet-header">
                <h3>폴더로 이동</h3>
            </div>

            <div class="folder-breadcrumb">
                <template v-for="(crumb, i) in browserState.breadcrumb.value" :key="crumb.id ?? 'root'">
                    <span v-if="i > 0" class="folder-breadcrumb-sep">/</span>
                    <button type="button" class="folder-breadcrumb-btn" @click="browserLogic.goToBreadcrumb(i)">{{ crumb.name }}</button>
                </template>
            </div>

            <div class="folder-picker-list">
                <button
                    v-for="folder in browserState.subfolders.value"
                    :key="folder.id"
                    class="action-sheet-btn"
                    type="button"
                    @click="browserLogic.openFolder(folder)"
                >
                    <i data-lucide="folder"></i>
                    {{ folder.name }}
                </button>
                <p v-if="!browserState.isLoading.value && browserState.subfolders.value.length === 0" class="folder-picker-empty">하위 폴더 없음</p>
            </div>

            <button class="action-sheet-btn action-sheet-btn-primary" type="button" @click="onConfirmMoveHere">
                <i data-lucide="check"></i>
                여기로 이동
            </button>
            <button class="action-sheet-btn action-sheet-btn-cancel" type="button" @click="logic.closeMovePicker">닫기</button>
        </div>
    </div>
</template>
