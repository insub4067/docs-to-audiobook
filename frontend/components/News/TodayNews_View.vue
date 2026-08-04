<script setup lang="ts">
import { onMounted, ref } from "vue";
import type { ReaderLogic } from "../../Reader/Reader_Logic.vue";

interface NewsItem {
    id: string;
    title: string;
    news_category: string | null;
    news_source: string | null;
    created_at: string;
    audio_url: string;
    sentences_url: string | null;
}

const props = defineProps<{ logic: ReaderLogic }>();

const items = ref<NewsItem[]>([]);
const loading = ref(true);

function formatRelativeTime(iso: string): string {
    const diffMin = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
    if (diffMin < 1) return "방금 전";
    if (diffMin < 60) return `${diffMin}분 전`;
    const diffHour = Math.floor(diffMin / 60);
    if (diffHour < 24) return `${diffHour}시간 전`;
    return `${Math.floor(diffHour / 24)}일 전`;
}

async function loadNews(): Promise<void> {
    try {
        const response = await fetch("/api/news");
        if (!response.ok) return;
        const data = await response.json();
        items.value = data.news || [];
    } catch (error) {
        console.error("오늘의 뉴스를 불러오지 못했습니다:", error);
    } finally {
        loading.value = false;
    }
}

async function onNewsClick(item: NewsItem): Promise<void> {
    let sentences = [];
    if (item.sentences_url) {
        try {
            const response = await fetch(item.sentences_url);
            if (response.ok) sentences = await response.json();
        } catch (error) {
            console.error("뉴스 문장 데이터를 불러오지 못했습니다:", error);
        }
    }
    props.logic.openSharedReaderMode(item.title, sentences, item.audio_url, null);
}

onMounted(loadNews);
</script>

<template>
    <section v-if="!loading && items.length > 0" class="glass-card library-section">
        <div class="card-header">
            <i data-lucide="newspaper" class="header-icon"></i>
            <h2>오늘의 뉴스</h2>
        </div>
        <div class="library-container">
            <div class="audio-list">
                <button
                    v-for="item in items"
                    :key="item.id"
                    type="button"
                    class="audio-item audio-item-news"
                    @click="onNewsClick(item)"
                >
                    <div class="audio-item-front">
                        <div class="audio-title-group">
                            <i data-lucide="play-circle"></i>
                            <div class="audio-title-col">
                                <span class="audio-title">{{ item.title }}</span>
                                <span class="audio-subtitle">
                                    <template v-if="item.news_category">{{ item.news_category }} · </template>
                                    <template v-if="item.news_source">{{ item.news_source }} · </template>{{ formatRelativeTime(item.created_at) }}
                                </span>
                            </div>
                        </div>
                    </div>
                </button>
            </div>
        </div>
    </section>
</template>
