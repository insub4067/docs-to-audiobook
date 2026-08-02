<script setup lang="ts">
import { onMounted, onUnmounted } from "vue";
import BaseToast from "./components/BaseToast.vue";

// lucide는 <i data-lucide="..."> 를 실제 svg로 바꿔치기하는 방식이라, DOM이
// 바뀔 때마다(메뉴 열림, 목록 렌더 등) 다시 호출해야 새로 생긴 아이콘도
// 그려진다. 컴포넌트마다 각자 호출하게 하는 대신(원본 vanilla JS는 그렇게
// 했고, 빠뜨리기 쉬웠다 — 지금 헤더에서 실제로 빠뜨렸다) 앱 전체를
// MutationObserver로 지켜보고 한 곳에서 처리한다.
let observer: MutationObserver | null = null;
let scheduled = false;

function scheduleCreateIcons() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
        scheduled = false;
        (window as any).lucide?.createIcons();
    });
}

onMounted(() => {
    scheduleCreateIcons();
    observer = new MutationObserver(scheduleCreateIcons);
    observer.observe(document.getElementById("app")!, { childList: true, subtree: true });
});

onUnmounted(() => observer?.disconnect());
</script>

<template>
    <div class="app-container">
        <router-view></router-view>
    </div>
    <BaseToast />
</template>
