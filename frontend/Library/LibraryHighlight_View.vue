<script setup lang="ts">
// 홈의 서점 카드. 경제 뉴스 카드 바로 아래에 온다.
//
// ⚠️ 특정 작품 id를 박아 넣지 않는다. 지금은 오디세이를 띄우는 것이 목적이지만,
// 그 작품을 내리거나 다른 것으로 바꾸면 홈 카드가 조용히 깨지고 원인을 찾기
// 어렵다. 뉴스 카드가 "가장 최근 기사 한 건"을 보여주는 것과 같은 규칙으로
// 가장 최근 작품을 보여준다 — 새 작품을 올리면 자연히 그것이 온다.
import { computed, onMounted } from "vue";
import type { ReaderLogic } from "../Reader/Reader_Logic.vue";
import { useLibraryState } from "./Library_State.vue";
import { useLibraryLogic } from "./Library_Logic.vue";
import { nowPlayingId, nowPlayingState } from "../services/nowPlaying";
import ListRowPlaceholderView from "../components/Placeholder/ListRowPlaceholder_View.vue";

const props = defineProps<{ logic: ReaderLogic }>();
const emit = defineEmits<{ (event: "more"): void }>();

const state = useLibraryState();
const libraryLogic = useLibraryLogic(state, props.logic);

// /api/library가 최신순으로 내려준다. 맨 앞이 가장 최근에 등록한 작품이다.
const topItem = computed(() => state.items.value[0] ?? null);

// 시리즈는 지금 듣고 있는 것이 작품 행이 아니라 그 안의 부다. 작품 id만
// 보면 2부부터는 "재생 중" 표시가 사라진다.
const isCurrent = computed(() => {
    const item = topItem.value;
    if (!item) return false;
    if (nowPlayingId.value === item.id) return true;
    return state.queueWork.value?.id === item.id
        && state.queueParts.value.some((part) => part.id === nowPlayingId.value);
});
const isPlaying = computed(() => isCurrent.value && nowPlayingState.value === "playing");

function formatDuration(seconds: number | null | undefined): string {
    if (!seconds) return "";
    const minutes = Math.round(seconds / 60);
    if (minutes < 60) return `약 ${minutes}분`;
    return `약 ${Math.floor(minutes / 60)}시간 ${minutes % 60}분`;
}

const subtitle = computed(() => {
    const item = topItem.value;
    if (!item) return "";
    const parts = [];
    if (item.library_category) parts.push(item.library_category);
    if ((item.part_count ?? 1) > 1) parts.push(`전 ${item.part_count}부`);
    const duration = formatDuration(item.total_duration_seconds ?? item.duration_seconds);
    if (duration) parts.push(duration);
    return parts.join(" · ");
});

onMounted(() => {
    if (!state.loaded.value) libraryLogic.loadLibrary();
});
</script>

<template>
    <!-- 뉴스 카드와 같은 이유로, 아직 못 받아 왔으면 감추지 않고 자리표시자를
         그린다. 나중에 끼워 넣으면 아래 내용이 밀려 누르려던 것이 움직인다.
         다 받아 왔는데 작품이 없을 때만 카드를 감춘다. -->
    <section v-if="!state.loaded.value || topItem" class="glass-card library-section">
        <div class="card-header">
            <i data-lucide="library" class="header-icon"></i>
            <h2>서점</h2>
            <button v-if="topItem" type="button" class="news-more-btn" @click="emit('more')">
                더보기
                <i data-lucide="chevron-right"></i>
            </button>
        </div>
        <div class="library-container">
            <div v-if="!state.loaded.value" class="audio-list">
                <ListRowPlaceholderView />
            </div>
            <div v-else class="audio-list">
                <button
                    type="button"
                    class="audio-item audio-item-news"
                    :class="{ 'is-playing': isCurrent, 'is-paused': isCurrent && !isPlaying }"
                    @click="libraryLogic.openDetail(topItem!)"
                >
                    <div class="audio-item-front">
                        <div class="audio-title-group">
                            <span class="row-play-icon">
                                <i data-lucide="book-open"></i>
                                <span class="row-play-bars" aria-hidden="true"><span></span><span></span><span></span></span>
                            </span>
                            <div class="audio-title-col">
                                <span class="audio-title">{{ topItem!.title }}</span>
                                <span class="audio-subtitle">{{ subtitle }}</span>
                            </div>
                        </div>
                    </div>
                </button>
            </div>
        </div>
    </section>
</template>
