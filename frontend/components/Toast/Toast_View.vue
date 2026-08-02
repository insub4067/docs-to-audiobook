<script setup lang="ts">
import { computed, nextTick, watch } from "vue";
import { useToastState } from "./Toast_State.vue";
import { useToastLogic } from "./Toast_Logic.vue";

// static/js/toast.js의 마크업(#toast/#toastIcon/#toastMessage)과 style.css의
// .toast/.toast-{type}/.toast-top 규칙을 그대로 재사용한다.
const { message, type, visible, isTop } = useToastState();
const { dismissToast } = useToastLogic(useToastState());

const iconName = computed(() => {
    if (type.value === "success") return "check-circle";
    if (type.value === "error") return "alert-triangle";
    return "info";
});

const toastClass = computed(() => [
    "toast",
    `toast-${type.value}`,
    { show: visible.value, "toast-top": isTop.value },
]);

// lucide는 <i data-lucide="..."> 를 실제 svg로 바꿔치기하는 방식이라,
// 아이콘 이름이 바뀔 때마다 다시 호출해야 한다.
watch(iconName, () => {
    nextTick(() => (window as any).lucide?.createIcons());
});
</script>

<template>
    <div id="toast" :class="toastClass" role="status" aria-live="polite" @click="dismissToast">
        <i id="toastIcon" :data-lucide="iconName"></i>
        <span id="toastMessage">{{ message }}</span>
    </div>
</template>
