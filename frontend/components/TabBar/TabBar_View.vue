<script setup lang="ts">
defineProps<{
    activeTab: "home" | "library" | "files";
}>();

const emit = defineEmits<{
    (e: "select", tab: "home" | "library" | "files"): void;
}>();
</script>

<template>
    <nav class="tab-bar" role="tablist" aria-label="화면 전환">
        <button
            type="button"
            class="tab-bar-btn"
            :class="{ active: activeTab === 'home' }"
            role="tab"
            :aria-selected="activeTab === 'home'"
            @click="emit('select', 'home')"
        >
            <i data-lucide="home"></i>
            <span>홈</span>
        </button>
        <button
            type="button"
            class="tab-bar-btn"
            :class="{ active: activeTab === 'library' }"
            role="tab"
            :aria-selected="activeTab === 'library'"
            @click="emit('select', 'library')"
        >
            <i data-lucide="library"></i>
            <span>라이브러리</span>
        </button>
        <button
            type="button"
            class="tab-bar-btn"
            :class="{ active: activeTab === 'files' }"
            role="tab"
            :aria-selected="activeTab === 'files'"
            @click="emit('select', 'files')"
        >
            <i data-lucide="folder"></i>
            <span>내 파일</span>
        </button>
    </nav>
</template>
