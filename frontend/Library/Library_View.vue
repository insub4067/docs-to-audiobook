<script setup lang="ts">
import { computed, onMounted, watch } from "vue";
import type { ReaderLogic } from "../Reader/Reader_Logic.vue";
import { useLibraryState, type LibraryItem, type LibrarySortKey } from "./Library_State.vue";
import { useLibraryLogic } from "./Library_Logic.vue";

const props = defineProps<{ logic: ReaderLogic; hasMiniPlayer?: boolean; active?: boolean; readerOpen?: boolean }>();
const state = useLibraryState();
const libraryLogic = useLibraryLogic(state, props.logic);

const categories = computed(() => {
    const set = new Set<string>();
    for (const item of state.items.value) if (item.library_category) set.add(item.library_category);
    return [...set];
});

/** 제목만으로는 원하는 판본을 찾기 어렵다 — 번역자·출처·설명까지 훑는다. */
function matchesQuery(item: LibraryItem, query: string): boolean {
    const haystack = [
        item.title, item.library_category, item.library_edition,
        item.library_translator, item.library_source, item.library_description,
    ].filter(Boolean).join(" ").toLowerCase();
    return query.split(/\s+/).every((word) => haystack.includes(word));
}

const SORT_LABELS: Record<LibrarySortKey, string> = {
    recent: "최근 추가",
    listening: "듣는 중",
    "duration-asc": "짧은 작품",
    "duration-desc": "긴 작품",
};
const SORT_KEYS = Object.keys(SORT_LABELS) as LibrarySortKey[];

const filteredItems = computed(() => {
    let items = state.items.value;
    if (state.activeCategory.value) {
        items = items.filter((item) => item.library_category === state.activeCategory.value);
    }
    const query = state.searchQuery.value.trim().toLowerCase();
    if (query) items = items.filter((item) => matchesQuery(item, query));

    // 원본 배열을 정렬하면 서버가 준 순서를 잃는다.
    const sorted = [...items];
    const key = state.sortKey.value;
    if (key === "duration-asc") sorted.sort((a, b) => (a.duration_seconds || 0) - (b.duration_seconds || 0));
    else if (key === "duration-desc") sorted.sort((a, b) => (b.duration_seconds || 0) - (a.duration_seconds || 0));
    else if (key === "listening") {
        // 듣던 작품을 위로. 다 들은 것은 아래로 내린다.
        const rank = (item: LibraryItem) => {
            const progress = libraryLogic.getProgress(item);
            if (!progress) return 1;
            return progress.isFinished ? 2 : 0;
        };
        sorted.sort((a, b) => rank(a) - rank(b));
    }
    return sorted;
});

function metaLine(item: LibraryItem): string {
    const parts: string[] = [];
    if (item.library_category) parts.push(item.library_category);
    if (item.library_edition) parts.push(item.library_edition);
    return parts.join(" · ");
}

function statsLine(item: LibraryItem): string {
    const parts: string[] = [];
    if (item.library_chapter_count) parts.push(`총 ${item.library_chapter_count}장`);
    if (item.duration_seconds) {
        const hours = Math.floor(item.duration_seconds / 3600);
        const minutes = Math.round((item.duration_seconds % 3600) / 60);
        if (hours > 0) parts.push(`약 ${hours}시간 ${minutes}분`);
        else if (minutes > 0) parts.push(`약 ${minutes}분`);
        else parts.push("1분 미만");
    }
    return parts.join(" · ");
}

function progressOf(item: LibraryItem) {
    return libraryLogic.getProgress(item);
}

onMounted(() => {
    if (!state.loaded.value) libraryLogic.loadLibrary();
    libraryLogic.loadSaves();
    libraryLogic.loadPlaybackPositions();
});

// v-show로 항상 마운트돼 있는 탭이라 onMounted는 앱 실행 중 딱 한 번만
// 불린다 — 관리자가 앱을 새로 열지 않고 작품을 발행해도 목록에 바로
// 반영되도록, 탭이 다시 활성화될 때마다 새로 불러온다.
watch(() => props.active, (active) => {
    if (!active) return;
    libraryLogic.loadLibrary();
    // 듣다가 돌아온 경우 진행률이 바로 반영돼야 한다.
    libraryLogic.loadPlaybackPositions();
});

// 이 탭에서 바로 작품을 듣고 리더를 닫으면 탭 전환이 일어나지 않는다.
// 그래서 위 watch만으로는 방금 들은 만큼이 카드에 반영되지 않았다.
// 리더가 닫히는 순간에도 다시 불러온다. 닫으면서 보내는 저장 요청과
// 겹칠 수 있지만, 재생 중 30초마다 저장한 값이 이미 서버에 있어
// 막대는 정상적으로 그려진다(최대 30초 뒤처질 뿐이다).
watch(() => props.readerOpen, (open, wasOpen) => {
    if (wasOpen && !open) libraryLogic.loadPlaybackPositions();
});
</script>

<template>
    <main class="app-main library-root" :class="{ 'has-mini-player': hasMiniPlayer }">
        <div class="glass-card library-section">
            <div class="card-header">
                <i data-lucide="library" class="header-icon"></i>
                <h2>라이브러리</h2>
            </div>
            <p class="action-sheet-hint" style="padding: 0 0 16px;">무료로 듣는 고전과 경전</p>

            <div class="library-search">
                <i data-lucide="search" class="library-search-icon"></i>
                <input
                    v-model="state.searchQuery.value"
                    type="search"
                    class="library-search-input"
                    placeholder="작품·번역자·출처 검색"
                    aria-label="라이브러리 검색"
                >
            </div>

            <div class="library-category-chips">
                <button
                    v-for="key in SORT_KEYS"
                    :key="key"
                    type="button"
                    class="library-chip library-sort-chip"
                    :class="{ active: state.sortKey.value === key }"
                    @click="state.sortKey.value = key"
                >{{ SORT_LABELS[key] }}</button>
            </div>

            <div v-if="categories.length > 1" class="library-category-chips">
                <button
                    type="button"
                    class="library-chip"
                    :class="{ active: state.activeCategory.value === null }"
                    @click="libraryLogic.selectCategory(null)"
                >전체</button>
                <button
                    v-for="category in categories"
                    :key="category"
                    type="button"
                    class="library-chip"
                    :class="{ active: state.activeCategory.value === category }"
                    @click="libraryLogic.selectCategory(category)"
                >{{ category }}</button>
            </div>

            <div v-if="state.loaded.value && filteredItems.length === 0" class="library-empty">
                <i data-lucide="book-open"></i>
                <template v-if="state.searchQuery.value.trim()">
                    <p>검색 결과가 없어요.</p>
                    <span>다른 낱말로 찾아보세요.</span>
                </template>
                <template v-else>
                    <p>아직 등록된 작품이 없어요.</p>
                    <span>곧 새로운 작품이 추가될 예정이에요.</span>
                </template>
            </div>

            <div class="audio-list">
                <!-- "이어 듣기"를 안에 넣어야 해서 행 자체는 button이 아니다
                     — button 안에 button은 중첩할 수 없다. -->
                <div
                    v-for="item in filteredItems"
                    :key="item.id"
                    class="audio-item audio-item-news"
                    role="button"
                    tabindex="0"
                    @click="libraryLogic.openDetail(item)"
                    @keydown.enter="libraryLogic.openDetail(item)"
                    @keydown.space.prevent="libraryLogic.openDetail(item)"
                >
                    <div class="audio-item-front">
                        <div class="audio-title-group">
                            <i data-lucide="book-open"></i>
                            <div class="audio-title-col">
                                <span class="audio-title">{{ item.title }}</span>
                                <span v-if="item.library_description" class="library-card-description">{{ item.library_description }}</span>
                                <span class="audio-subtitle">{{ metaLine(item) }}</span>
                                <span v-if="statsLine(item)" class="audio-subtitle">{{ statsLine(item) }}</span>

                                <template v-if="progressOf(item)">
                                    <span v-if="progressOf(item)!.isFinished" class="library-progress-done">모두 들음</span>
                                    <div v-else class="library-progress">
                                        <div class="library-progress-track">
                                            <div class="library-progress-fill" :style="{ width: progressOf(item)!.percent + '%' }"></div>
                                        </div>
                                        <span class="audio-subtitle">{{ progressOf(item)!.percent }}% · {{ progressOf(item)!.remainingLabel }}</span>
                                        <button
                                            type="button"
                                            class="library-resume-btn"
                                            @click.stop="libraryLogic.playFromLastPosition(item)"
                                        >이어 듣기</button>
                                    </div>
                                </template>
                            </div>
                            <i v-if="libraryLogic.isSaved(item)" data-lucide="check-circle-2" class="library-saved-badge" aria-label="내 서재에 있음"></i>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </main>
</template>
