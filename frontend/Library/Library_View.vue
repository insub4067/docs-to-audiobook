<script setup lang="ts">
import { computed, onMounted } from "vue";
import type { ReaderLogic } from "../Reader/Reader_Logic.vue";
import { useLibraryState } from "./Library_State.vue";
import { useLibraryLogic } from "./Library_Logic.vue";

const props = defineProps<{ logic: ReaderLogic; hasMiniPlayer?: boolean }>();
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

onMounted(() => {
    if (!state.loaded.value) libraryLogic.loadLibrary();
    libraryLogic.loadSaves();
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

            <div v-if="categories.length > 0" class="library-category-chips">
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
                <button
                    v-for="item in filteredItems"
                    :key="item.id"
                    type="button"
                    class="audio-item audio-item-news"
                    @click="libraryLogic.openDetail(item)"
                >
                    <div class="audio-item-front">
                        <div class="audio-title-group">
                            <i data-lucide="book-open"></i>
                            <div class="audio-title-col">
                                <span class="audio-title">{{ item.title }}</span>
                                <span class="audio-subtitle">
                                    <template v-if="item.library_category">{{ item.library_category }} · </template>
                                    <template v-if="item.library_edition">{{ item.library_edition }}</template>
                                </span>
                            </div>
                        </div>
                    </div>
                </button>
            </div>
        </div>
    </main>
</template>
