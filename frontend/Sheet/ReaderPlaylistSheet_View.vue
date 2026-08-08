<script setup lang="ts">
import { computed } from "vue";
import type { ReaderState } from "../Reader/Reader_State.vue";
import type { ReaderLogic } from "../Reader/Reader_Logic.vue";
import type { AudioListState } from "../components/Library/AudioList_State.vue";
import { getAudiobookDisplayTitle } from "../utils/format";
import { nowPlayingId } from "../services/nowPlaying";
import {
    usePlaylistNavigation, isNewsItem, type PlaylistItem,
} from "../components/MiniPlayer/playlistNavigation";

const props = defineProps<{
    state: ReaderState;
    logic: ReaderLogic;
    audioListState: AudioListState;
}>();

// 미니 플레이어 스와이프와 같은 목록·같은 현재 위치를 봐야 한다.
const playlist = usePlaylistNavigation(props.state, props.audioListState, props.logic);
const playlistItems = playlist.items;
const isNewsPlaylist = computed(() => props.state.sharedPlaylistKind.value === "news");

function itemTitle(item: PlaylistItem): string {
    return isNewsItem(item) ? item.title : getAudiobookDisplayTitle(item.title);
}

// ⚠️ 목록 안의 자리가 아니라 "지금 재생 중인 id"로 판정한다. 자리로 보면
// 목록이 바뀌거나 다른 문서를 재생했을 때 엉뚱한 행에 표시가 남는다.
function isPlaying(item: PlaylistItem): boolean {
    return nowPlayingId.value === item.id;
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
                <h3>{{ isNewsPlaylist ? "경제 뉴스" : "재생목록" }}</h3>
            </div>
            <div class="playlist-list-scroll">
                <div class="audio-list">
                    <button
                        v-for="item in playlistItems"
                        :key="item.id"
                        type="button"
                        class="audio-item audio-item-news"
                        :class="{ 'is-playing': isPlaying(item) }"
                        :aria-current="isPlaying(item) ? 'true' : undefined"
                        @click="onItemClick(item)"
                    >
                        <div class="audio-item-front">
                            <div class="audio-title-group">
                                <!-- ⚠️ lucide가 <i>를 <svg>로 갈아치우므로 이 아이콘을
                                     v-if/v-show로 토글하면 안 된다. Vue의 vnode가 사라진
                                     <i>를 가리키게 돼 크래시가 난다(프로필 화면에서 겪었다).
                                     아이콘은 그대로 두고 표시를 덧붙인다. -->
                                <i data-lucide="play-circle"></i>
                                <span class="audio-title">{{ itemTitle(item) }}</span>
                                <span v-if="isPlaying(item)" class="now-playing-bars" aria-hidden="true">
                                    <span></span><span></span><span></span>
                                </span>
                            </div>
                        </div>
                    </button>
                </div>
            </div>
            <button class="action-sheet-btn action-sheet-btn-cancel" type="button" @click="logic.closePlaylistSheet">닫기</button>
        </div>
    </div>
</template>
