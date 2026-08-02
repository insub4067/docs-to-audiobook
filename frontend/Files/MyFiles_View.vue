<script setup lang="ts">
import { computed, onMounted } from "vue";
import type { AudioListState } from "../components/Library/AudioList_State.vue";
import type { AudioListLogic } from "../components/Library/AudioList_Logic.vue";
import type { MyFilesState } from "./MyFiles_State.vue";
import type { MyFilesLogic } from "./MyFiles_Logic.vue";
import { useFolderBrowserState } from "./FolderBrowser_State.vue";
import { useFolderBrowserLogic } from "./FolderBrowser_Logic.vue";
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

function onNewFolder(): void {
    const name = window.prompt("새 폴더 이름");
    if (name) browserLogic.createFolder(name);
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
            <div v-for="folder in browserState.subfolders.value" :key="folder.id" class="myfiles-row" @click="browserLogic.openFolder(folder)">
                <i data-lucide="folder" class="myfiles-row-icon"></i>
                <span class="myfiles-row-title">{{ folder.name }}</span>
                <button class="btn-icon-round btn-more" title="더보기" type="button" @click.stop="myFilesLogic.openFolderActionSheet(folder)">
                    <i data-lucide="more-horizontal"></i>
                </button>
            </div>

            <AudioListItemView v-for="audio in currentFolderAudiobooks" :key="audio.id" :audio="audio" :logic="audioListLogic" />
        </div>

        <ActionSheetView :state="audioListState" :logic="audioListLogic" :my-files-logic="myFilesLogic" />
        <FolderActionSheetView :state="myFilesState" :logic="myFilesLogic" :folder-browser-logic="browserLogic" />
        <MoveToFolderSheetView :state="myFilesState" :logic="myFilesLogic" :audio-list-logic="audioListLogic" />
    </div>
</template>
