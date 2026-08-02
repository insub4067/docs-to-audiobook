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

function onNewFolder(): void {
    const name = window.prompt("새 폴더 이름");
    if (name) browserLogic.createFolder(name);
}

onMounted(() => browserLogic.loadCurrentFolder());
</script>

<template>
    <section class="glass-card library-section">
        <div class="card-header">
            <i data-lucide="folder" class="header-icon"></i>
            <h2>내 파일</h2>
            <button
                class="btn-icon"
                aria-label="새 폴더"
                title="새 폴더"
                style="margin-left: auto; width: 44px; height: 44px; border-radius: 50%; background: var(--glass-bg); border: 1px solid var(--glass-border); display: flex; align-items: center; justify-content: center; cursor: pointer; color: var(--text-color); transition: all 0.3s ease;"
                @click="onNewFolder"
            >
                <i data-lucide="folder-plus" style="width: 18px; height: 18px;"></i>
            </button>
        </div>

        <div class="folder-breadcrumb">
            <template v-for="(crumb, i) in browserState.breadcrumb.value" :key="crumb.id ?? 'root'">
                <span v-if="i > 0" class="folder-breadcrumb-sep">/</span>
                <button type="button" class="folder-breadcrumb-btn" @click="browserLogic.goToBreadcrumb(i)">{{ crumb.name }}</button>
            </template>
        </div>

        <div class="library-container">
            <div class="library-empty" v-show="isEmpty">
                <i data-lucide="folder-open"></i>
                <p>이 폴더는 비어 있습니다.</p>
            </div>

            <div class="audio-list">
                <div v-for="folder in browserState.subfolders.value" :key="folder.id" class="audio-item" @click="browserLogic.openFolder(folder)">
                    <div class="audio-item-front">
                        <div class="audio-title-group">
                            <i data-lucide="folder"></i>
                            <span class="audio-title">{{ folder.name }}</span>
                        </div>
                        <div class="audio-actions">
                            <button class="btn-icon-round btn-more" title="더보기" @click.stop="myFilesLogic.openFolderActionSheet(folder)">
                                <i data-lucide="more-horizontal"></i>
                            </button>
                        </div>
                    </div>
                </div>

                <AudioListItemView v-for="audio in currentFolderAudiobooks" :key="audio.id" :audio="audio" :logic="audioListLogic" />
            </div>
        </div>
    </section>

    <ActionSheetView :state="audioListState" :logic="audioListLogic" :my-files-logic="myFilesLogic" />
    <FolderActionSheetView :state="myFilesState" :logic="myFilesLogic" :folder-browser-logic="browserLogic" />
    <MoveToFolderSheetView :state="myFilesState" :logic="myFilesLogic" :audio-list-logic="audioListLogic" />
</template>
