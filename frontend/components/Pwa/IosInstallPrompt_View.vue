<script setup lang="ts">
import type { PwaState } from "./Pwa_State.vue";
import type { PwaLogic } from "./Pwa_Logic.vue";

defineProps<{ state: PwaState; logic: PwaLogic }>();
</script>

<template>
    <div id="iosPwaPrompt" class="ios-pwa-prompt" :class="{ show: state.isIosPromptVisible.value }">
        <button class="pwa-close-btn" aria-label="닫기" @click="logic.dismissIosPrompt">
            <i data-lucide="x"></i>
        </button>
        <div class="pwa-prompt-content">
            <div class="pwa-icon">
                <img :src="'/static/textaudio-icon.png'" alt="TextAudio 아이콘" style="width: 40px; height: 40px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
            </div>
            <div class="pwa-text">
                <p>앱처럼 빠르고 편하게 사용하세요!</p>
                <span>
                    하단의 <b>공유</b>
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:text-bottom;margin:0 2px;"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"></path><polyline points="16 6 12 2 8 6"></polyline><line x1="12" y1="2" x2="12" y2="15"></line></svg>
                    아이콘을 누르고<br><b>'홈 화면에 추가'</b>
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:text-bottom;margin:0 2px;"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><line x1="12" y1="8" x2="12" y2="16"></line><line x1="8" y1="12" x2="16" y2="12"></line></svg>
                    를 선택해주세요.
                </span>
            </div>
        </div>
    </div>
</template>
