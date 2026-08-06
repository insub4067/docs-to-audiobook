<script setup lang="ts">
import { computed, onMounted, watch } from "vue";
import type { ReaderLogic } from "../Reader/Reader_Logic.vue";
import { useLibraryState, type LibraryItem } from "./Library_State.vue";
import { useLibraryLogic } from "./Library_Logic.vue";

const props = defineProps<{ logic: ReaderLogic; hasMiniPlayer?: boolean; active?: boolean }>();
const state = useLibraryState();
const libraryLogic = useLibraryLogic(state, props.logic);

const categories = computed(() => {
    const set = new Set<string>();
    for (const item of state.items.value) if (item.library_category) set.add(item.library_category);
    return [...set];
});

const filteredItems = computed(() => {
    if (!state.activeCategory.value) return state.items.value;
    return state.items.value.filter((item) => item.library_category === state.activeCategory.value);
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
</script>

<template>
    <main class="app-main library-root" :class="{ 'has-mini-player': hasMiniPlayer }">
        <div class="glass-card library-section">
            <div class="card-header">
                <i data-lucide="library" class="header-icon"></i>
                <h2>라이브러리</h2>
            </div>
            <p class="action-sheet-hint" style="padding: 0 0 16px;">무료로 듣는 고전과 경전</p>

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
                <p>아직 등록된 작품이 없어요.</p>
                <span>곧 새로운 작품이 추가될 예정이에요.</span>
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
