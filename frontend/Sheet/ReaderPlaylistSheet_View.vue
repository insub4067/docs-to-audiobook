<script setup lang="ts">
import { computed } from "vue";
import type { ReaderState } from "../Reader/Reader_State.vue";
import type { ReaderLogic } from "../Reader/Reader_Logic.vue";
import type { AudioListState } from "../components/Library/AudioList_State.vue";
import { getAudiobookDisplayTitle } from "../utils/format";
import { nowPlayingId, nowPlayingState } from "../services/nowPlaying";
import {
    usePlaylistNavigation, isNewsItem, isLibraryPart, type PlaylistItem,
} from "../components/MiniPlayer/playlistNavigation";
import { useLibraryState } from "../Library/Library_State.vue";

const props = defineProps<{
    state: ReaderState;
    logic: ReaderLogic;
    audioListState: AudioListState;
}>();

// 미니 플레이어 스와이프와 같은 목록·같은 현재 위치를 봐야 한다.
const playlist = usePlaylistNavigation(props.state, props.audioListState, props.logic);
const playlistItems = playlist.items;
const libraryState = useLibraryState();
const isNewsPlaylist = computed(() => props.state.sharedPlaylistKind.value === "news");
const isLibraryPlaylist = computed(() => props.state.sharedPlaylistKind.value === "library");

// 시리즈는 작품명이 시트 제목에 한 번 나오므로, 목록에는 부 제목만 적는다.
// 줄마다 "오디세이 · 제3권..."을 반복하면 정작 다른 부와 구분되는 부분이
// 오른쪽으로 밀려 잘린다.
const sheetTitle = computed(() => {
    if (isNewsPlaylist.value) return "경제 뉴스";
    if (isLibraryPlaylist.value) return libraryState.queueWork.value?.title ?? "재생목록";
    return "재생목록";
});

function itemTitle(item: PlaylistItem): string {
    if (isLibraryPart(item)) return item.part_title;
    return isNewsItem(item) ? item.title : getAudiobookDisplayTitle(item.title);
}

function isCurrent(item: PlaylistItem): boolean {
    return nowPlayingId.value === item.id;
}

function isItemPlaying(item: PlaylistItem): boolean {
    return isCurrent(item) && nowPlayingState.value === "playing";
}

function onItemClick(item: PlaylistItem): void {
    playlist.open(item);
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
                <h3>{{ sheetTitle }}</h3>
            </div>
            <div class="playlist-list-scroll">
                <div class="audio-list">
                    <button
                        v-for="item in playlistItems"
                        :key="item.id"
                        type="button"
                        class="audio-item audio-item-news"
                        :class="{ 'is-playing': isCurrent(item), 'is-paused': isCurrent(item) && !isItemPlaying(item) }"
                        :aria-current="isCurrent(item) ? 'true' : undefined"
                        @click="onItemClick(item)"
                    >
                        <div class="audio-item-front">
                            <div class="audio-title-group">
                                <span class="row-play-icon">
                                    <i data-lucide="play-circle"></i>
                                    <span class="row-play-bars" aria-hidden="true"><span></span><span></span><span></span></span>
                                </span>
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
