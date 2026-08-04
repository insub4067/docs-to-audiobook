<script setup lang="ts">
import { computed, onMounted } from "vue";
import type { ReaderLogic } from "../../Reader/Reader_Logic.vue";
import { useNewsState } from "./News_State.vue";
import { useNewsLogic } from "./News_Logic.vue";

const props = defineProps<{ logic: ReaderLogic }>();
const state = useNewsState();
const newsLogic = useNewsLogic(state, props.logic);

const topItem = computed(() => state.items.value[0] ?? null);

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
    <section v-if="topItem" class="glass-card library-section">
        <div class="card-header">
            <i data-lucide="newspaper" class="header-icon"></i>
            <h2>경제 뉴스</h2>
            <button type="button" class="news-more-btn" @click="newsLogic.openList">
                더보기
                <i data-lucide="chevron-right"></i>
            </button>
        </div>
        <div class="library-container">
            <div class="audio-list">
                <button type="button" class="audio-item audio-item-news" @click="newsLogic.openNewsItem(topItem)">
                    <div class="audio-item-front">
                        <div class="audio-title-group">
                            <i data-lucide="play-circle"></i>
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
