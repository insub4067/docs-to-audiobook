<script setup lang="ts">
import { computed, onMounted } from "vue";
import type { AudioListState } from "./AudioList_State.vue";
import type { AudioListLogic } from "./AudioList_Logic.vue";
import type { GeneratingItem } from "../../Generation/Generation_State.vue";
import type { AudiobookRecord } from "../../services/indexedDb";
import type { MyFilesLogic } from "../../Files/MyFiles_Logic.vue";
import AudioListItemView from "./AudioListItem_View.vue";
import ActionSheetView from "../../Sheet/ActionSheet_View.vue";

const props = withDefaults(defineProps<{
    state: AudioListState;
    logic: AudioListLogic;
    myFilesLogic: MyFilesLogic;
    generatingItems: GeneratingItem[];
    onImportLink?: () => void;
    items?: AudiobookRecord[];
    title?: string;
    icon?: string;
    showImportButton?: boolean;
    showGeneratingItems?: boolean;
    hideActionSheet?: boolean;
    autoLoad?: boolean;
    emptyTitle?: string;
    emptyHint?: string;
}>(), {
    title: "내 오디오북",
    icon: "folder-heart",
    showImportButton: true,
    showGeneratingItems: true,
    hideActionSheet: false,
    autoLoad: true,
    emptyTitle: "아직 생성된 책이 없습니다.",
    emptyHint: "새로운 문서를 업로드해 보세요.",
});

const displayedItems = computed(() => props.items ?? props.state.savedAudiobooks.value);

/** 합성이 끝나기 전에 앞 구간부터 듣는다. */
function onListenEarly(item: GeneratingItem): void {
    if (!item.playableAudio) return;
    const url = URL.createObjectURL(item.playableAudio);
    (window as any).__openPartialReaderMode?.(item.title, item.playableSentences ?? [], url);
}

const isEmpty = computed(() =>
    (!props.showGeneratingItems || (props.generatingItems.length === 0 && props.state.backgroundJobItems.value.length === 0))
    && displayedItems.value.length === 0
);

onMounted(() => {
    if (props.autoLoad) props.logic.load();
});
</script>

<template>
    <section class="glass-card library-section">
        <div class="card-header">
            <i :data-lucide="icon" class="header-icon"></i>
            <h2>{{ title }}</h2>
            <button
                v-if="showImportButton"
                class="btn-icon"
                aria-label="공유 링크 불러오기"
                style="margin-left: auto; width: 44px; height: 44px; border-radius: 50%; background: var(--glass-bg); border: 1px solid var(--glass-border); display: flex; align-items: center; justify-content: center; cursor: pointer; color: var(--text-color); transition: all 0.3s ease;"
                @click="onImportLink"
            >
                <i data-lucide="link" style="width: 18px; height: 18px;"></i>
            </button>
        </div>

        <div class="library-container">
            <div class="library-empty" v-show="isEmpty">
                <i data-lucide="music"></i>
                <p>{{ emptyTitle }}</p>
                <span>{{ emptyHint }}</span>
            </div>

            <div class="audio-list">
                <template v-if="showGeneratingItems">
                    <div v-for="item in generatingItems" :key="item.id" class="audio-item audio-item-generating">
                        <div class="audio-title-group">
                            <div class="generating-spinner"></div>
                            <div class="generating-info">
                                <span class="audio-title">{{ item.title }}</span>
                                <div class="generating-progress-track">
                                    <div class="generating-progress-fill" :style="{ width: item.progressPercent + '%' }"></div>
                                </div>
                                <span class="generating-status">{{ item.statusText }}</span>
                            </div>
                        </div>
                        <!-- 나머지가 합성되는 동안 앞 구간부터 듣게 한다.
                             10만 자 문서면 전체는 70초 넘게 걸리지만 첫 구간은
                             2초면 준비되고 그것만으로 100초 분량이다. -->
                        <button
                            v-if="item.playableAudio"
                            class="generating-listen-btn"
                            type="button"
                            @click.stop="onListenEarly(item)"
                        >
                            <i data-lucide="play"></i>
                            <span>먼저 듣기</span>
                        </button>
                    </div>

                    <div v-for="item in state.backgroundJobItems.value" :key="item.jobId" class="audio-item audio-item-generating">
                        <div class="audio-title-group">
                            <div class="generating-spinner"></div>
                            <div class="generating-info">
                                <span class="audio-title">{{ item.title }}</span>
                                <span class="generating-status">서버에서 생성 중...</span>
                            </div>
                        </div>
                    </div>
                </template>

                <AudioListItemView v-for="audio in displayedItems" :key="audio.id" :audio="audio" :logic="logic" :swipe-enabled="false" />
            </div>
        </div>
    </section>

    <ActionSheetView v-if="!hideActionSheet" :state="state" :logic="logic" :my-files-logic="myFilesLogic" />
</template>
