<script setup lang="ts">
import { onMounted, onUnmounted } from "vue";
import BaseToast from "./components/BaseToast.vue";
import PullRefreshIndicatorView from "./components/Pwa/PullRefreshIndicator_View.vue";
import IosInstallPromptView from "./components/Pwa/IosInstallPrompt_View.vue";
import { usePwaState } from "./composables/Pwa/Pwa_State.vue";
import { usePwaLogic } from "./composables/Pwa/Pwa_Logic.vue";

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

const pwaState = usePwaState();
const pwaLogic = usePwaLogic(pwaState);

onMounted(() => {
    scheduleCreateIcons();
    observer = new MutationObserver(scheduleCreateIcons);
    observer.observe(document.getElementById("app")!, { childList: true, subtree: true });

    window.addEventListener("touchstart", pwaLogic.onTouchStart, { passive: true });
    window.addEventListener("touchmove", pwaLogic.onTouchMove, { passive: false });
    window.addEventListener("touchend", pwaLogic.onTouchEnd, { passive: true });
    window.addEventListener("touchcancel", pwaLogic.onTouchCancel, { passive: true });
    pwaLogic.initialize();
});

onUnmounted(() => {
    observer?.disconnect();
    window.removeEventListener("touchstart", pwaLogic.onTouchStart);
    window.removeEventListener("touchmove", pwaLogic.onTouchMove);
    window.removeEventListener("touchend", pwaLogic.onTouchEnd);
    window.removeEventListener("touchcancel", pwaLogic.onTouchCancel);
});
</script>

<template>
    <div class="background-decor">
        <div class="circle circle-1"></div>
        <div class="circle circle-2"></div>
        <div class="circle circle-3"></div>
    </div>
    <PullRefreshIndicatorView :state="pwaState" />

    <div class="app-container">
        <router-view></router-view>
    </div>
    <BaseToast />
    <IosInstallPromptView :state="pwaState" :logic="pwaLogic" />
</template>
