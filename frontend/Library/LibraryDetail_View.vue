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

// 여러 부로 나뉜 작품인가. 목차를 문장 데이터에서 뽑을지, 부 목록으로
// 대신할지를 가른다.
const parts = computed(() => props.state.detailParts.value);
const isSeries = computed(() => (props.state.detailItem.value?.part_count ?? 1) > 1);

// 재생 중 표시는 작품 id만 보면 시리즈에서 1부에만 붙는다. 지금 듣는 부가
// 이 작품에 속하는지까지 본다.
const isCurrent = computed(() => {
    const item = props.state.detailItem.value;
    if (!item) return false;
    if (nowPlayingId.value === item.id) return true;
    return parts.value.some((part) => part.id === nowPlayingId.value);
});
const isPlaying = computed(() => isCurrent.value && nowPlayingState.value === "playing");

function isPartCurrent(partId: string): boolean {
    return nowPlayingId.value === partId;
}

/** 부가 얼마나 재생됐는지. 목록 카드와 같은 기준(97%)으로 "들음"을 본다. */
function partProgressPercent(partId: string, durationSeconds: number | null): number {
    const seconds = props.state.playbackSeconds.value[partId];
    if (!seconds || !durationSeconds) return 0;
    return Math.min(Math.round((seconds / durationSeconds) * 100), 100);
}

function formatPartDuration(seconds: number | null): string {
    if (!seconds) return "";
    const minutes = Math.round(seconds / 60);
    return minutes < 60 ? `${minutes}분` : `${Math.floor(minutes / 60)}시간 ${minutes % 60}분`;
}

watch(() => props.state.detailItem.value, async (item) => {
    toc.value = [];
    rawSentences.value = [];
    hasPlaybackHistory.value = false;
    if (!item) return;

    // 시리즈는 목차를 부 목록으로 대신한다. 작품 대표 행의 문장 데이터를
    // 읽어 봐야 그건 1부 안의 소제목이라 목차로 쓸 수 없다.
    if ((item.part_count ?? 1) > 1) {
        hasPlaybackHistory.value = Object.keys(props.state.playbackSeconds.value).length > 0
            && props.state.detailParts.value.some((part) => props.state.playbackSeconds.value[part.id] > 0);
        return;
    }

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

// 부 목록은 상세를 연 뒤에 도착한다. 도착하고 나서야 "이어 듣기"를 보여줄지
// 알 수 있다 — 재생 위치가 부마다 따로 저장되기 때문이다.
watch(parts, (loaded) => {
    if (!isSeries.value) return;
    hasPlaybackHistory.value = loaded.some((part) => props.state.playbackSeconds.value[part.id] > 0);
});

function onChapterClick(entry: TocEntry): void {
    const item = props.state.detailItem.value;
    if (!item) return;
    props.logic.playFromChapter(item, rawSentences.value, entry.startMs / 1000);
}

function onPartClick(index: number): void {
    const item = props.state.detailItem.value;
    if (!item) return;
    void props.logic.playPart(item, parts.value, index);
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
                    <button type="button" class="action-sheet-btn" @click="logic.share(state.detailItem.value)">
                        <i data-lucide="share-2"></i>
                        공유하기
                    </button>
                </div>

                <!-- 여러 부로 나뉜 작품은 목차 자리에 부 목록이 온다. 여기서
                     고른 부부터 끝까지 이어서 재생된다. -->
                <div v-if="isSeries && state.isLoadingParts.value" class="library-detail-section" aria-hidden="true">
                    <h4>목차</h4>
                    <div class="index-sheet-list">
                        <span class="redacted redacted-toc" style="width: 72%"></span>
                        <span class="redacted redacted-toc" style="width: 58%"></span>
                        <span class="redacted redacted-toc" style="width: 66%"></span>
                    </div>
                </div>

                <div v-else-if="isSeries && parts.length > 0" class="library-detail-section">
                    <h4>목차 <span class="library-part-count">전 {{ parts.length }}부</span></h4>
                    <div class="index-sheet-list">
                        <button
                            v-for="(part, idx) in parts"
                            :key="part.id"
                            type="button"
                            class="library-part-item"
                            :class="{ 'is-playing': isPartCurrent(part.id) }"
                            :aria-current="isPartCurrent(part.id) ? 'true' : undefined"
                            @click="onPartClick(idx)"
                        >
                            <span class="library-part-main">
                                <span class="library-part-title">{{ part.part_title }}</span>
                                <span class="library-part-meta">
                                    <template v-if="isPartCurrent(part.id)">{{ isPlaying ? '재생 중' : '일시정지' }}</template>
                                    <template v-else-if="partProgressPercent(part.id, part.duration_seconds) > 0">
                                        {{ partProgressPercent(part.id, part.duration_seconds) }}% 들음
                                    </template>
                                    <template v-else>{{ formatPartDuration(part.duration_seconds) }}</template>
                                </span>
                            </span>
                            <span
                                v-if="partProgressPercent(part.id, part.duration_seconds) > 0"
                                class="library-part-progress"
                                aria-hidden="true"
                            >
                                <span :style="{ width: partProgressPercent(part.id, part.duration_seconds) + '%' }"></span>
                            </span>
                        </button>
                    </div>
                </div>

                <!-- 단권의 목차는 문장 데이터를 받아 와야 만들어진다. 자리를 안 잡아
                     두면 상세를 연 뒤 아래쪽에 목차가 통째로 끼어들며 화면이 뛴다. -->
                <div v-else-if="isLoadingToc" class="library-detail-section" aria-hidden="true">
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
