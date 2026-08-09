<script setup lang="ts">
import { ref, computed, watch } from "vue";
import type { LibraryState } from "./Library_State.vue";
import type { LibraryLogic } from "./Library_Logic.vue";
import { nowPlayingId, nowPlayingState } from "../services/nowPlaying";

interface TocEntry {
    text: string;
    level: number;
    startMs: number;
}

const props = defineProps<{
    state: LibraryState;
    logic: LibraryLogic;
}>();

const toc = ref<TocEntry[]>([]);
const rawSentences = ref<unknown[]>([]);
const isLoadingToc = ref(false);
const hasPlaybackHistory = ref(false);
const isCurrent = computed(() => props.state.detailItem.value ? nowPlayingId.value === props.state.detailItem.value.id : false);
const isPlaying = computed(() => isCurrent.value && nowPlayingState.value === "playing");

watch(() => props.state.detailItem.value, async (item) => {
    toc.value = [];
    rawSentences.value = [];
    hasPlaybackHistory.value = false;
    if (!item) return;
    isLoadingToc.value = true;
    try {
        const [sentences, lastPosition] = await Promise.all([
            props.logic.loadSentences(item),
            props.logic.getLastPosition(item),
        ]);
        rawSentences.value = sentences;
        toc.value = (sentences as { type?: string; display?: string; level?: number; start?: number }[])
            .filter((s) => s.type === "heading")
            .map((s) => ({ text: s.display || "", level: s.level || 1, startMs: s.start || 0 }));
        hasPlaybackHistory.value = lastPosition > 0;
    } finally {
        isLoadingToc.value = false;
    }
});

function onChapterClick(entry: TocEntry): void {
    const item = props.state.detailItem.value;
    if (!item) return;
    props.logic.playFromChapter(item, rawSentences.value, entry.startMs / 1000);
}
</script>

<template>
    <div class="library-detail-overlay" :class="{ show: state.isDetailOpen.value }" role="dialog" aria-modal="true" aria-label="작품 상세">
        <div v-if="state.detailItem.value" class="library-detail-container">
            <header class="library-detail-header">
                <button class="btn-reader-close" type="button" aria-label="닫기" @click="logic.closeDetail">
                    <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"></polyline></svg>
                </button>
                <h3 class="reader-book-title">{{ state.detailItem.value.title }}</h3>
                <span style="width: 22px;"></span>
            </header>

            <div class="library-detail-content">
                <p class="library-detail-meta">
                    <template v-if="state.detailItem.value.library_category">{{ state.detailItem.value.library_category }} · </template>
                    <template v-if="state.detailItem.value.library_edition">{{ state.detailItem.value.library_edition }}</template>
                </p>

                <p v-if="state.detailItem.value.library_description" class="library-detail-description">
                    {{ state.detailItem.value.library_description }}
                </p>

                <div v-if="isCurrent" class="library-detail-now-playing">
                    <span class="detail-play-bars" :class="{ paused: !isPlaying }" aria-hidden="true"><span></span><span></span><span></span></span>
                    {{ isPlaying ? '재생 중' : '일시정지' }}
                </div>

                <div class="library-detail-actions">
                    <button type="button" class="action-sheet-btn action-sheet-btn-primary" @click="logic.playFromStart(state.detailItem.value)">
                        <i data-lucide="play"></i>
                        처음부터 듣기
                    </button>
                    <button v-if="hasPlaybackHistory" type="button" class="action-sheet-btn" @click="logic.playFromLastPosition(state.detailItem.value)">
                        <i data-lucide="rotate-ccw"></i>
                        이어 듣기
                    </button>
                    <button
                        type="button"
                        class="action-sheet-btn"
                        :class="{ 'library-saved-state': logic.isSaved(state.detailItem.value) }"
                        @click="logic.toggleSave(state.detailItem.value)"
                    >
                        <i :data-lucide="logic.isSaved(state.detailItem.value) ? 'check' : 'plus'"></i>
                        {{ logic.isSaved(state.detailItem.value) ? "내 서재에 추가됨" : "내 서재에 추가" }}
                    </button>
                </div>

                <!-- 목차는 문장 데이터를 받아 와야 만들어진다. 자리를 안 잡아
                     두면 상세를 연 뒤 아래쪽에 목차가 통째로 끼어들며 화면이 뛴다. -->
                <div v-if="isLoadingToc" class="library-detail-section" aria-hidden="true">
                    <h4>목차</h4>
                    <div class="index-sheet-list">
                        <span class="redacted redacted-toc" style="width: 72%"></span>
                        <span class="redacted redacted-toc" style="width: 58%"></span>
                        <span class="redacted redacted-toc" style="width: 66%"></span>
                    </div>
                </div>

                <div v-else-if="toc.length > 0" class="library-detail-section">
                    <h4>목차</h4>
                    <div class="index-sheet-list">
                        <div
                            v-for="(entry, idx) in toc"
                            :key="idx"
                            :class="`index-item h${entry.level}`"
                            @click="onChapterClick(entry)"
                        >{{ entry.text }}</div>
                    </div>
                </div>

                <div class="library-detail-section library-detail-rights">
                    <h4>판본 및 출처</h4>
                    <p v-if="state.detailItem.value.library_translator"><b>번역/편저</b> {{ state.detailItem.value.library_translator }}</p>
                    <p v-if="state.detailItem.value.library_source"><b>출처</b> {{ state.detailItem.value.library_source }}</p>
                    <p v-if="state.detailItem.value.library_rights"><b>이용 조건</b> {{ state.detailItem.value.library_rights }}</p>
                </div>
            </div>
        </div>
    </div>
</template>
