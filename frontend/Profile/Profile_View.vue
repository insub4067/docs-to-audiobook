<script setup lang="ts">
import { computed, ref } from "vue";
import { useAuthStore } from "../stores/auth";
import { useAuthLogic } from "../Auth/Auth_Logic.vue";
import type { ThemeLogic } from "../Theme/Theme_Logic.vue";
import type { ReaderControlsState } from "../Reader/ReaderControls/ReaderControls_State.vue";
import type { ReaderControlsLogic } from "../Reader/ReaderControls/ReaderControls_Logic.vue";
import {
    REPEAT_LABELS, FONT_FAMILY_LABELS, FONT_SIZE_LABELS, LINE_HEIGHT_LABELS,
} from "../Reader/ReaderControls/ReaderControls_Logic.vue";

const props = defineProps<{
    themeLogic: ThemeLogic;
    controlsState: ReaderControlsState;
    controlsLogic: ReaderControlsLogic;
}>();

const authStore = useAuthStore();
const authLogic = useAuthLogic();

const isSettingsExpanded = ref(false);

const profileName = computed(() => authStore.user?.full_name || authStore.user?.email || "사용자");
const profileInitial = computed(() => profileName.value.trim().split(/\s+/)[0].slice(0, 2));

async function handleLogout(): Promise<void> {
    await authLogic.logout();
}
</script>

<template>
    <main class="app-main profile-root">
        <div class="glass-card profile-section" v-if="authStore.isLoggedIn">
            <div class="profile-account-row">
                <span class="profile-avatar" aria-hidden="true">{{ profileInitial }}</span>
                <div class="profile-account-info">
                    <strong>{{ profileName }}</strong>
                    <span>{{ authStore.user?.email }}</span>
                </div>
            </div>
            <a v-if="authStore.isAdmin" class="myfiles-row" href="/admin">
                <i data-lucide="layout-dashboard" class="myfiles-row-icon"></i>
                <span class="myfiles-row-title">관리자 페이지</span>
                <i data-lucide="chevron-right" class="myfiles-row-chevron"></i>
            </a>
            <button class="myfiles-row" type="button" @click="handleLogout">
                <i data-lucide="log-out" class="myfiles-row-icon"></i>
                <span class="myfiles-row-title">로그아웃</span>
            </button>
        </div>
        <div class="glass-card profile-section" v-else>
            <p class="action-sheet-hint">상단의 "Google 계정으로 로그인" 버튼을 눌러 로그인하면 오디오북이 기기 간에 동기화돼요.</p>
        </div>

        <div class="glass-card profile-section">
            <button
                class="card-header profile-settings-toggle"
                type="button"
                :aria-expanded="isSettingsExpanded"
                @click="isSettingsExpanded = !isSettingsExpanded"
            >
                <i data-lucide="settings-2" class="header-icon"></i>
                <h2>읽기 설정</h2>
                <i data-lucide="chevron-down" class="profile-settings-toggle-chevron" :class="{ 'is-expanded': isSettingsExpanded }"></i>
            </button>
            <template v-if="isSettingsExpanded">
            <button class="myfiles-row" type="button" @click="themeLogic.openSheet">
                <i data-lucide="palette" class="myfiles-row-icon"></i>
                <span class="myfiles-row-title">읽기 화면 테마</span>
                <i data-lucide="chevron-right" class="myfiles-row-chevron"></i>
            </button>
            <button class="myfiles-row" type="button" @click="controlsLogic.openSheet('fontFamily')">
                <i data-lucide="type" class="myfiles-row-icon"></i>
                <span class="myfiles-row-title">글꼴</span>
                <span class="myfiles-row-value">{{ FONT_FAMILY_LABELS[controlsState.fontFamily.value] }}</span>
                <i data-lucide="chevron-right" class="myfiles-row-chevron"></i>
            </button>
            <button class="myfiles-row" type="button" @click="controlsLogic.openSheet('fontSize')">
                <i data-lucide="case-sensitive" class="myfiles-row-icon"></i>
                <span class="myfiles-row-title">글자 크기</span>
                <span class="myfiles-row-value">{{ FONT_SIZE_LABELS[controlsState.fontSize.value] }}</span>
                <i data-lucide="chevron-right" class="myfiles-row-chevron"></i>
            </button>
            <button class="myfiles-row" type="button" @click="controlsLogic.openSheet('lineHeight')">
                <i data-lucide="align-justify" class="myfiles-row-icon"></i>
                <span class="myfiles-row-title">줄 간격</span>
                <span class="myfiles-row-value">{{ LINE_HEIGHT_LABELS[controlsState.lineHeight.value] }}</span>
                <i data-lucide="chevron-right" class="myfiles-row-chevron"></i>
            </button>
            <button class="myfiles-row" type="button" @click="controlsLogic.openSheet('speed')">
                <i data-lucide="gauge" class="myfiles-row-icon"></i>
                <span class="myfiles-row-title">재생 속도</span>
                <span class="myfiles-row-value">{{ controlsState.playbackSpeed.value }}x</span>
                <i data-lucide="chevron-right" class="myfiles-row-chevron"></i>
            </button>
            <button class="myfiles-row" type="button" @click="controlsLogic.openSheet('repeat')">
                <i data-lucide="repeat" class="myfiles-row-icon"></i>
                <span class="myfiles-row-title">반복 모드</span>
                <span class="myfiles-row-value">{{ REPEAT_LABELS[controlsState.repeatMode.value] }}</span>
                <i data-lucide="chevron-right" class="myfiles-row-chevron"></i>
            </button>
            <button class="myfiles-row" type="button" @click="controlsLogic.openSheet('timer')">
                <i data-lucide="moon" class="myfiles-row-icon"></i>
                <span class="myfiles-row-title">취침 타이머</span>
                <span class="myfiles-row-value">{{ controlsState.timerLabel.value }}</span>
                <i data-lucide="chevron-right" class="myfiles-row-chevron"></i>
            </button>
            </template>
        </div>
    </main>
</template>
