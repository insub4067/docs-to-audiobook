<script setup lang="ts">
import { ref, watch } from "vue";
import type { AudioListState } from "./AudioList_State.vue";
import type { AudioListLogic } from "./AudioList_Logic.vue";
import { useSwipeToDismiss } from "../../utils/swipeToDismiss";
import { useToastLogic } from "../../composables/Toast/Toast_Logic.vue";
import { useToastState } from "../../composables/Toast/Toast_State.vue";

const props = defineProps<{
    state: AudioListState;
    logic: AudioListLogic;
}>();

const { showToast } = useToastLogic(useToastState());
const sheet = ref<HTMLElement | null>(null);

function close(): void {
    props.logic.closeActionSheet();
}

useSwipeToDismiss(sheet, close);

watch(() => props.state.isActionSheetOpen.value, (open) => {
    document.body.style.overflow = open ? "hidden" : "";
});

function onBackdropClick(event: MouseEvent): void {
    if (event.target === event.currentTarget) close();
}

async function onShare(): Promise<void> {
    const target = props.state.actionSheetTarget.value;
    close();
    if (target) await props.logic.performShare(target);
}

async function onDownload(): Promise<void> {
    const target = props.state.actionSheetTarget.value;
    close();
    if (target) await props.logic.downloadAudiobook(target);
}

async function onEditTitle(): Promise<void> {
    const target = props.state.actionSheetTarget.value;
    if (!target || target.isDefault) return;
    close();
    await props.logic.editAudiobookTitle(target);
}

async function onDelete(): Promise<void> {
    const target = props.state.actionSheetTarget.value;
    if (!target) return;
    if (target.isDefault) {
        close();
        showToast("기본 제공 오디오북은 삭제할 수 없습니다.", "error");
        return;
    }
    const id = target.id;
    close();
    await props.logic.deleteAudiobook(id);
}
</script>

<template>
    <div
        class="action-sheet-backdrop"
        :class="{ show: state.isActionSheetOpen.value }"
        role="dialog"
        aria-modal="true"
        aria-label="오디오북 작업"
        @click="onBackdropClick"
    >
        <div class="action-sheet" ref="sheet">
            <div class="action-sheet-handle"></div>
            <button class="action-sheet-btn" @click="onShare">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg>
                공유
            </button>
            <button class="action-sheet-btn" @click="onDownload">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                다운로드
            </button>
            <button v-if="!state.actionSheetTarget.value?.isDefault" class="action-sheet-btn" @click="onEditTitle">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"></path><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"></path></svg>
                제목 수정
            </button>
            <button v-if="!state.actionSheetTarget.value?.isDefault" class="action-sheet-btn action-sheet-btn-danger" @click="onDelete">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                삭제
            </button>
            <button class="action-sheet-btn action-sheet-btn-cancel" @click="close">닫기</button>
        </div>
    </div>
</template>
