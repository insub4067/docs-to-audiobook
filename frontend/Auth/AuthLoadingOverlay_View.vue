<script setup lang="ts">
import { useAuthStore } from "../stores/auth";

const authStore = useAuthStore();
</script>

<template>
    <div class="loading-overlay" :class="{ show: authStore.isBusy }" role="alert" aria-live="assertive">
        <div class="loading-card">
            <div class="spinner-container">
                <div class="double-bounce1"></div>
                <div class="double-bounce2"></div>
            </div>
            <h3>{{ authStore.busyMessage }}</h3>
            <p class="loading-overlay-warning">완료될 때까지 화면을 벗어나지 마세요</p>
        </div>
    </div>
</template>
