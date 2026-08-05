<script setup lang="ts">
import { ref, watch } from "vue";
import type { ReaderLogic } from "../../Reader/Reader_Logic.vue";
import { useNewsState } from "./News_State.vue";
import { useNewsLogic } from "./News_Logic.vue";
import { useSwipeToDismiss } from "../../utils/swipeToDismiss";

const props = defineProps<{ logic: ReaderLogic }>();
const state = useNewsState();
const newsLogic = useNewsLogic(state, props.logic);

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
                </div>
            </div>
            <button
                v-if="state.items.value.length > 1"
                type="button"
                class="news-play-all-btn"
                @click="newsLogic.playAll"
            >
                <i data-lucide="list-music"></i>
                전체 듣기
            </button>
            <div class="news-list-scroll">
                <div class="audio-list">
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
            <button class="action-sheet-btn action-sheet-btn-cancel" type="button" @click="newsLogic.closeList">닫기</button>
        </div>
    </div>
</template>
