<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { ReaderLogic } from "../../Reader/Reader_Logic.vue";
import { useNewsState } from "./News_State.vue";
import { useNewsLogic } from "./News_Logic.vue";
import { useSwipeToDismiss } from "../../utils/swipeToDismiss";
import NewsPlaceholderRowView from "./NewsPlaceholderRow_View.vue";

const props = defineProps<{ logic: ReaderLogic }>();
const state = useNewsState();
const newsLogic = useNewsLogic(state, props.logic);

// "재생 범위가 뭔지 모호하다"는 피드백에 맞춰, 몇 개를 얼마나 듣게
// 되는지를 헤더 부제와 버튼 라벨에 직접 명시한다.
const listSubtitle = computed(() => {
    const count = state.items.value.length;
    if (!count) return null;
    const totalSeconds = state.items.value.reduce((sum, item) => sum + (item.duration_seconds || 0), 0);
    const parts = [`총 ${count}개`];
    if (totalSeconds > 0) {
        const minutes = Math.round(totalSeconds / 60);
        parts.push(minutes > 0 ? `약 ${minutes}분` : "1분 미만");
    }
    return parts.join(" · ");
});

const playAllLabel = computed(() => {
    const count = state.items.value.length;
    return count > 0 ? `경제 뉴스 ${count}개 연속 듣기` : "경제 뉴스 연속 듣기";
});

const sheet = ref<HTMLElement | null>(null);
const handle = ref<HTMLElement | null>(null);
// 손잡이(핸들+제목) 영역에서 시작한 드래그만 시트를 닫는다 — 목록
// 영역은 스크롤 위치와 무관하게 항상 네이티브 스크롤에만 반응해야
// 한다(안 그러면 목록 맨 위에서 살짝만 당겨도 시트가 통째로 끌려
// 내려오는 것처럼 보인다).
useSwipeToDismiss(sheet, () => newsLogic.closeList(), handle);

watch(() => state.isListOpen.value, (open) => {
    document.body.style.overflow = open ? "hidden" : "";
});

function onBackdropClick(event: MouseEvent): void {
    if (event.target === event.currentTarget) newsLogic.closeList();
}

function formatRelativeTime(iso: string): string {
    const diffMin = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
    if (diffMin < 1) return "방금 전";
    if (diffMin < 60) return `${diffMin}분 전`;
    const diffHour = Math.floor(diffMin / 60);
    if (diffHour < 24) return `${diffHour}시간 전`;
    return `${Math.floor(diffHour / 24)}일 전`;
}
</script>

<template>
    <div
        class="action-sheet-backdrop"
        :class="{ show: state.isListOpen.value }"
        role="dialog"
        aria-modal="true"
        aria-label="경제 뉴스"
        @click="onBackdropClick"
    >
        <div class="action-sheet news-list-sheet" ref="sheet">
            <div ref="handle">
                <div class="action-sheet-handle"></div>
                <div class="index-sheet-header">
                    <h3>경제 뉴스</h3>
                    <p v-if="listSubtitle" class="action-sheet-subtitle">{{ listSubtitle }}</p>
                </div>
            </div>
            <div class="news-list-scroll">
                <!-- 시트를 열자마자 목록이 있는 경우가 대부분이지만, 서명 URL이
                     오래돼 다시 받아 오는 동안에는 비어 있을 수 있다. 빈 시트
                     대신 자리표시자를 보여 준다. 너비를 다르게 준 건 진짜
                     목록처럼 보이게 하려는 것이다. -->
                <div v-if="!state.loaded.value" class="audio-list">
                    <NewsPlaceholderRowView title-width="88%" />
                    <NewsPlaceholderRowView title-width="72%" />
                    <NewsPlaceholderRowView title-width="80%" />
                </div>
                <div v-else class="audio-list">
                    <button
                        v-for="item in state.items.value"
                        :key="item.id"
                        type="button"
                        class="audio-item audio-item-news"
                        @click="newsLogic.openNewsItem(item)"
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
            <div class="news-list-footer">
                <button
                    type="button"
                    class="news-play-all-btn"
                    :disabled="state.items.value.length === 0"
                    @click="newsLogic.playAll"
                >
                    <i data-lucide="list-music"></i>
                    {{ playAllLabel }}
                </button>
                <button class="action-sheet-btn action-sheet-btn-cancel" type="button" @click="newsLogic.closeList">닫기</button>
            </div>
        </div>
    </div>
</template>
