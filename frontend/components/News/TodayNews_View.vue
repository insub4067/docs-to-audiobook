<script setup lang="ts">
import { computed, onMounted } from "vue";
import type { ReaderLogic } from "../../Reader/Reader_Logic.vue";
import { useNewsState } from "./News_State.vue";
import { useNewsLogic } from "./News_Logic.vue";
import { nowPlayingId, nowPlayingState } from "../../services/nowPlaying";
import ListRowPlaceholderView from "../Placeholder/ListRowPlaceholder_View.vue";

const props = defineProps<{ logic: ReaderLogic }>();
const state = useNewsState();
const newsLogic = useNewsLogic(state, props.logic);

const topItem = computed(() => state.items.value[0] ?? null);
const isCurrent = computed(() => topItem.value ? nowPlayingId.value === topItem.value.id : false);
const isPlaying = computed(() => isCurrent.value && nowPlayingState.value === "playing");

function formatRelativeTime(iso: string): string {
    const diffMin = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
    if (diffMin < 1) return "방금 전";
    if (diffMin < 60) return `${diffMin}분 전`;
    const diffHour = Math.floor(diffMin / 60);
    if (diffHour < 24) return `${diffHour}시간 전`;
    return `${Math.floor(diffHour / 24)}일 전`;
}

onMounted(() => {
    if (!state.loaded.value) newsLogic.loadNews();
});
</script>

<template>
    <!-- 아직 못 받아 왔으면 카드를 숨기지 않고 자리표시자를 그린다. 숨겼다가
         나중에 끼워 넣으면 그 아래 내용이 통째로 밀려, 누르려던 것이 움직인다.
         다 받아 왔는데 뉴스가 없을 때만 카드를 감춘다. -->
    <section v-if="!state.loaded.value || topItem" class="glass-card library-section">
        <div class="card-header">
            <i data-lucide="newspaper" class="header-icon"></i>
            <h2>경제 뉴스</h2>
            <button
                v-if="topItem"
                type="button"
                class="news-more-btn"
                @click="newsLogic.openList"
            >
                더보기
                <i data-lucide="chevron-right"></i>
            </button>
        </div>
        <div class="library-container">
            <div v-if="!state.loaded.value" class="audio-list">
                <ListRowPlaceholderView />
            </div>
            <div v-else class="audio-list">
                <button type="button" class="audio-item audio-item-news" :class="{ 'is-playing': isCurrent, 'is-paused': isCurrent && !isPlaying }" @click="newsLogic.openNewsItem(topItem)">
                    <div class="audio-item-front">
                        <div class="audio-title-group">
                            <span class="row-play-icon">
                                <i data-lucide="play-circle"></i>
                                <span class="row-play-bars" aria-hidden="true"><span></span><span></span><span></span></span>
                            </span>
                            <div class="audio-title-col">
                                <span class="audio-title">{{ topItem.title }}</span>
                                <span class="audio-subtitle">
                                    <template v-if="topItem.news_category">{{ topItem.news_category }} · </template>
                                    <template v-if="topItem.news_source">{{ topItem.news_source }} · </template>{{ formatRelativeTime(topItem.created_at) }}
                                </span>
                            </div>
                        </div>
                    </div>
                </button>
            </div>
        </div>
    </section>
</template>
