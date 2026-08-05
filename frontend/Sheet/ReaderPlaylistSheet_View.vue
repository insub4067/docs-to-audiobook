<script setup lang="ts">
import { computed } from "vue";
import type { ReaderState } from "../Reader/Reader_State.vue";
import type { ReaderLogic } from "../Reader/Reader_Logic.vue";
import type { AudioListState } from "../components/Library/AudioList_State.vue";
import type { AudiobookRecord } from "../services/indexedDb";
import type { NewsItem } from "../components/News/News_State.vue";
import { useNewsState } from "../components/News/News_State.vue";
import { useNewsLogic } from "../components/News/News_Logic.vue";
import { getAudiobookDisplayTitle } from "../utils/format";

const props = defineProps<{
    state: ReaderState;
    logic: ReaderLogic;
    audioListState: AudioListState;
}>();

const newsState = useNewsState();
const newsLogic = useNewsLogic(newsState, props.logic);

const isNewsPlaylist = computed(() => props.state.sharedPlaylistKind.value === "news");

// 홈 요약 카드와 같은 이유로 폴더든 뉴스든 "같이 묶인 항목이 2개 이상"일
// 때만 고를 의미가 있다 — Reader_View의 제목 클릭 가능 여부도 이 값을 쓴다.
const playlistItems = computed<(AudiobookRecord | NewsItem)[]>(() => {
    if (isNewsPlaylist.value) return newsState.items.value;
    const folderId = props.state.currentAudioObject.value?.folderId;
    if (!folderId) return [];
    return props.audioListState.savedAudiobooks.value.filter((a) => a.folderId === folderId);
});

function isNewsItem(item: AudiobookRecord | NewsItem): item is NewsItem {
    return "audio_url" in item;
}

function itemTitle(item: AudiobookRecord | NewsItem): string {
    return isNewsItem(item) ? item.title : getAudiobookDisplayTitle(item.title);
}

function onItemClick(item: AudiobookRecord | NewsItem): void {
    if (isNewsItem(item)) newsLogic.openNewsItem(item);
    else props.logic.open(item);
    props.logic.closePlaylistSheet();
}

function onBackdropClick(event: MouseEvent): void {
    if (event.target === event.currentTarget) props.logic.closePlaylistSheet();
}
</script>

<template>
    <div
        class="action-sheet-backdrop"
        :class="{ show: state.isPlaylistSheetOpen.value }"
        role="dialog"
        aria-modal="true"
        aria-label="재생목록"
        @click="onBackdropClick"
    >
        <div class="action-sheet playlist-sheet">
            <div class="action-sheet-handle"></div>
            <div class="index-sheet-header">
                <h3>{{ isNewsPlaylist ? "경제 뉴스" : "재생목록" }}</h3>
            </div>
            <div class="playlist-list-scroll">
                <div class="audio-list">
                    <button
                        v-for="item in playlistItems"
                        :key="item.id"
                        type="button"
                        class="audio-item audio-item-news"
                        @click="onItemClick(item)"
                    >
                        <div class="audio-item-front">
                            <div class="audio-title-group">
                                <i data-lucide="play-circle"></i>
                                <span class="audio-title">{{ itemTitle(item) }}</span>
                            </div>
                        </div>
                    </button>
                </div>
            </div>
            <button class="action-sheet-btn action-sheet-btn-cancel" type="button" @click="logic.closePlaylistSheet">닫기</button>
        </div>
    </div>
</template>
