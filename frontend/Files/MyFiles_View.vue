<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import type { AudioListState } from "../components/Library/AudioList_State.vue";
import type { AudioListLogic } from "../components/Library/AudioList_Logic.vue";
import type { AudiobookRecord } from "../services/indexedDb";
import type { MyFilesState } from "./MyFiles_State.vue";
import type { MyFilesLogic } from "./MyFiles_Logic.vue";
import { useFolderBrowserState } from "./FolderBrowser_State.vue";
import { useFolderBrowserLogic } from "./FolderBrowser_Logic.vue";
import { getAudiobookDisplayTitle } from "../utils/format";
import AudioListItemView from "../components/Library/AudioListItem_View.vue";
import ActionSheetView from "../Sheet/ActionSheet_View.vue";
import FolderActionSheetView from "../Sheet/FolderActionSheet_View.vue";
import MoveToFolderSheetView from "../Sheet/MoveToFolderSheet_View.vue";

const props = defineProps<{
    audioListState: AudioListState;
    audioListLogic: AudioListLogic;
    myFilesState: MyFilesState;
    myFilesLogic: MyFilesLogic;
}>();

const browserState = useFolderBrowserState("내 파일");
const browserLogic = useFolderBrowserLogic(browserState);

const currentFolderAudiobooks = computed(() =>
    props.audioListState.savedAudiobooks.value.filter(
        (audio) => (audio.folderId ?? null) === browserState.currentFolderId.value
    )
);

const isEmpty = computed(() =>
    browserState.subfolders.value.length === 0 && currentFolderAudiobooks.value.length === 0
);

const isAtRoot = computed(() => browserState.breadcrumb.value.length <= 1);

// 폴더 안에 있을 때(!isAtRoot) 목록 맨 위에 "상위 폴더" 행을 두고, 여기로
// 파일을 끌어 놓으면 한 단계 위(부모 폴더가 없으면 루트)로 이동한다.
const parentFolderId = computed<string | null>(() => {
    const crumbs = browserState.breadcrumb.value;
    return crumbs.length >= 2 ? crumbs[crumbs.length - 2].id : null;
});

function goUpOneLevel(): void {
    browserLogic.goToBreadcrumb(browserState.breadcrumb.value.length - 2);
}

function onNewFolder(): void {
    const name = window.prompt("새 폴더 이름");
    if (name) browserLogic.createFolder(name);
}

// 오디오북 항목을 폴더 위에 길게 눌러 끌어다 놓으면 그 폴더로 이동한다.
// 롱프레스로 드래그 여부를 확정하기 전까지는 일정 이상 움직이면(스크롤/
// 탭으로 판단) 곧바로 취소해, AudioListItem_View 자체의 스와이프 삭제
// 제스처나 리스트 스크롤과 충돌하지 않도록 한다.
const LONG_PRESS_MS = 450;
const MOVE_CANCEL_PX = 10;
// "상위 폴더" 행의 data-folder-id에 쓰는 값 — 실제 폴더 id가 아니라, 놓는
// 시점에 parentFolderId로 다시 풀어낸다(부모가 루트면 null이 되어야 하는데
// data-* 속성엔 null을 담을 수 없어서 자리표시자가 필요하다).
const PARENT_DROP_TARGET = "__parent__";
const dragAudioId = ref<string | null>(null);
const dragOverFolderId = ref<string | null>(null);
// 드래그 중 손가락을 따라다니는 고스트(iOS 스타일 축소+반투명 미리보기)의
// 화면 좌표. .myfiles-list의 overflow:hidden에 잘리지 않도록 body에
// teleport해서 그린다.
const dragGhostTitle = ref("");
const dragGhostPos = ref<{ x: number; y: number } | null>(null);
let dragCandidate: AudiobookRecord | null = null;
let dragStartX = 0;
let dragStartY = 0;
let longPressTimer: ReturnType<typeof setTimeout> | null = null;

function clearLongPressTimer(): void {
    if (longPressTimer) clearTimeout(longPressTimer);
    longPressTimer = null;
}

function resetDragState(): void {
    clearLongPressTimer();
    dragCandidate = null;
    dragAudioId.value = null;
    dragOverFolderId.value = null;
    dragGhostPos.value = null;
}

function onDragTouchStart(event: TouchEvent, audio: AudiobookRecord): void {
    dragCandidate = audio;
    dragStartX = event.touches[0].clientX;
    dragStartY = event.touches[0].clientY;
    clearLongPressTimer();
    longPressTimer = setTimeout(() => {
        dragAudioId.value = audio.id;
        dragGhostTitle.value = getAudiobookDisplayTitle(audio.title);
        dragGhostPos.value = { x: dragStartX, y: dragStartY };
        if (navigator.vibrate) navigator.vibrate(30);
    }, LONG_PRESS_MS);
}

function onDragTouchMove(event: TouchEvent): void {
    if (!dragCandidate) return;
    const touch = event.touches[0];
    if (!dragAudioId.value) {
        const dx = Math.abs(touch.clientX - dragStartX);
        const dy = Math.abs(touch.clientY - dragStartY);
        if (dx > MOVE_CANCEL_PX || dy > MOVE_CANCEL_PX) resetDragState();
        return;
    }
    if (event.cancelable) event.preventDefault();
    dragGhostPos.value = { x: touch.clientX, y: touch.clientY };
    const target = document.elementFromPoint(touch.clientX, touch.clientY);
    const folderRow = (target as HTMLElement | null)?.closest<HTMLElement>(".myfiles-row[data-folder-id]");
    dragOverFolderId.value = folderRow?.dataset.folderId ?? null;
}

async function onDragTouchEnd(): Promise<void> {
    const audio = dragCandidate;
    const target = dragOverFolderId.value;
    resetDragState();
    if (!audio || !target) return;
    const folderId = target === PARENT_DROP_TARGET ? parentFolderId.value : target;
    await props.audioListLogic.moveToFolder(audio, folderId);
}

onMounted(() => browserLogic.loadCurrentFolder());
</script>

<template>
    <!-- 부모(Home_View)가 v-show로 탭 전환을 제어한다. Vue는 컴포넌트가
         루트 노드를 여러 개 가지면(fragment) 그 v-show를 어디에도 붙이지
         못하고 조용히 무시한다 — 그래서 반드시 이 화면 전체를 루트
         하나로 감싸야 한다(안의 시트들까지 포함해서). -->
    <div class="myfiles-root">
        <div class="myfiles-toolbar">
            <div class="folder-breadcrumb" v-if="!isAtRoot">
                <template v-for="(crumb, i) in browserState.breadcrumb.value" :key="crumb.id ?? 'root'">
                    <span v-if="i > 0" class="folder-breadcrumb-sep">/</span>
                    <button type="button" class="folder-breadcrumb-btn" @click="browserLogic.goToBreadcrumb(i)">{{ crumb.name }}</button>
                </template>
            </div>
            <span v-else></span>
            <button class="btn-icon-round btn-more" aria-label="새 폴더" title="새 폴더" type="button" @click="onNewFolder">
                <i data-lucide="folder-plus"></i>
            </button>
        </div>

        <div class="library-empty" v-show="isEmpty">
            <i data-lucide="folder-open"></i>
            <p>이 폴더는 비어 있습니다.</p>
        </div>

        <div class="myfiles-list">
            <div
                v-if="!isAtRoot"
                class="myfiles-row myfiles-row-parent"
                :class="{ 'drag-over': dragOverFolderId === PARENT_DROP_TARGET }"
                :data-folder-id="PARENT_DROP_TARGET"
                @click="goUpOneLevel"
            >
                <i data-lucide="corner-left-up" class="myfiles-row-icon"></i>
                <span class="myfiles-row-title">상위 폴더</span>
            </div>

            <div
                v-for="folder in browserState.subfolders.value"
                :key="folder.id"
                class="myfiles-row"
                :class="{ 'drag-over': dragOverFolderId === folder.id }"
                :data-folder-id="folder.id"
                @click="browserLogic.openFolder(folder)"
            >
                <i data-lucide="folder" class="myfiles-row-icon"></i>
                <span class="myfiles-row-title">{{ folder.name }}</span>
                <button class="btn-icon-round btn-more" title="더보기" type="button" @click.stop="myFilesLogic.openFolderActionSheet(folder)">
                    <i data-lucide="more-horizontal"></i>
                </button>
            </div>

            <AudioListItemView
                v-for="audio in currentFolderAudiobooks"
                :key="audio.id"
                :audio="audio"
                :logic="audioListLogic"
                @touchstart.passive="onDragTouchStart($event, audio)"
                @touchmove="onDragTouchMove"
                @touchend.passive="onDragTouchEnd"
                @touchcancel.passive="resetDragState"
            />
        </div>

        <ActionSheetView :state="audioListState" :logic="audioListLogic" :my-files-logic="myFilesLogic" />
        <FolderActionSheetView :state="myFilesState" :logic="myFilesLogic" :folder-browser-logic="browserLogic" />
        <MoveToFolderSheetView :state="myFilesState" :logic="myFilesLogic" :audio-list-logic="audioListLogic" />

        <!-- 리스트 행의 overflow:hidden에 잘리지 않도록 body에 그린다.
             주의: 이 컴포넌트는 Home_View가 v-show로 탭을 제어하므로 루트가
             하나여야 한다 — Teleport를 .myfiles-root 밖 형제로 빼면 다시
             다중 루트가 되어 v-show가 조용히 무시된다(과거에 겪은 버그). -->
        <Teleport to="body">
            <div
                v-if="dragGhostPos"
                class="drag-ghost"
                :style="{ left: dragGhostPos.x + 'px', top: dragGhostPos.y + 'px' }"
            >
                <i data-lucide="play-circle"></i>
                <span>{{ dragGhostTitle }}</span>
            </div>
        </Teleport>
    </div>
</template>
