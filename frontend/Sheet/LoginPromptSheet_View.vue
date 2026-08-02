<script setup lang="ts">
import { ref, watch } from "vue";
import type { GenerationState } from "../Generation/Generation_State.vue";
import type { GenerationLogic } from "../Generation/Generation_Logic.vue";
import { useSwipeToDismiss } from "../utils/swipeToDismiss";

const props = defineProps<{
    state: GenerationState;
    logic: GenerationLogic;
}>();

const sheet = ref<HTMLElement | null>(null);

function close(): void {
    props.state.isLoginPromptOpen.value = false;
}

useSwipeToDismiss(sheet, close);

watch(() => props.state.isLoginPromptOpen.value, (open) => {
    document.body.style.overflow = open ? "hidden" : "";
});

function onBackdropClick(event: MouseEvent): void {
    if (event.target === event.currentTarget) close();
}
</script>

<template>
    <div
        class="action-sheet-backdrop"
        :class="{ show: state.isLoginPromptOpen.value }"
        role="dialog"
        aria-modal="true"
        aria-label="로그인 안내"
        @click="onBackdropClick"
    >
        <div class="action-sheet" ref="sheet">
            <div class="action-sheet-handle"></div>
            <div class="login-prompt-body">
                <p class="login-prompt-title">추가 생성은 로그인 후 가능해요</p>
                <p class="login-prompt-desc">로그인하면 지금 설정 그대로 이어서 만들고, 기기에 저장된 체험본도 클라우드에 보관해요</p>
            </div>
            <button class="action-sheet-btn" @click="logic.onLoginPromptConfirm">
                <i data-lucide="log-in"></i>
                Google로 로그인하기
            </button>
            <button class="action-sheet-btn action-sheet-btn-cancel" @click="close">닫기</button>
        </div>
    </div>
</template>
