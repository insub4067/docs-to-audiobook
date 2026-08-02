<script setup lang="ts">
import HeaderView from "../components/AppHeader/Header_View.vue";
</script>

<template>
    <HeaderView />
    <main class="app-main" id="appMain">
        <!-- TODO: 업로드/생성(Generation), 보관함(Library), 리더(Reader)를
             차례로 포팅해 여기 채운다. 지금은 헤더(인증)만 검증한다. -->
        <p style="color: var(--text-muted); padding: 24px;">업로드/보관함 포팅 진행 중입니다.</p>
    </main>
</template>
