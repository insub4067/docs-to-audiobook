<script setup lang="ts">
import { computed, ref } from "vue";
import { useAuthStore } from "../stores/auth";
import { useAuthLogic } from "../Auth/Auth_Logic.vue";
import type { ThemeState } from "../Theme/Theme_State.vue";
import { APP_THEME_OPTIONS } from "../Theme/Theme_State.vue";
import type { ThemeLogic } from "../Theme/Theme_Logic.vue";
import type { ReaderControlsState } from "../Reader/ReaderControls/ReaderControls_State.vue";
import type { ReaderControlsLogic } from "../Reader/ReaderControls/ReaderControls_Logic.vue";
import {
    REPEAT_LABELS, FONT_FAMILY_LABELS, FONT_SIZE_LABELS, LINE_HEIGHT_LABELS,
} from "../Reader/ReaderControls/ReaderControls_Logic.vue";

const props = defineProps<{
    themeState: ThemeState;
    themeLogic: ThemeLogic;
    controlsState: ReaderControlsState;
    controlsLogic: ReaderControlsLogic;
    hasMiniPlayer?: boolean;
    active?: boolean;
}>();

const authStore = useAuthStore();
const authLogic = useAuthLogic();

const isSettingsExpanded = ref(false);
const isLogoutConfirmOpen = ref(false);

const profileName = computed(() => authStore.user?.full_name || authStore.user?.email || "사용자");
const profileInitial = computed(() => profileName.value.trim().split(/\s+/)[0].slice(0, 2));
const themeLabel = computed(() => APP_THEME_OPTIONS.find((o) => o.value === props.themeState.activeTheme.value)?.label ?? "");
const speedLabel = computed(() => `${props.controlsState.playbackSpeed.value.toFixed(1)}x`);

function openLogoutConfirm(): void {
    isLogoutConfirmOpen.value = true;
}
function closeLogoutConfirm(): void {
    isLogoutConfirmOpen.value = false;
}
async function confirmLogout(): Promise<void> {
    isLogoutConfirmOpen.value = false;
    await authLogic.logout();
}
function onLogoutBackdropClick(event: MouseEvent): void {
    if (event.target === event.currentTarget) closeLogoutConfirm();
}
</script>

<template>
    <main class="app-main profile-root" v-show="active" :class="{ 'has-mini-player': hasMiniPlayer }">
        <div class="glass-card profile-section profile-account-card" v-if="authStore.isLoggedIn">
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
        </div>
        <div class="glass-card profile-section" v-else>
            <p class="action-sheet-hint">상단의 "Google 계정으로 로그인" 버튼을 눌러 로그인하면 오디오북이 기기 간에 동기화돼요.</p>
        </div>

        <div class="glass-card profile-section profile-settings-card">
            <button
                class="card-header profile-settings-toggle"
                type="button"
                :aria-expanded="isSettingsExpanded"
                @click="isSettingsExpanded = !isSettingsExpanded"
            >
                <i data-lucide="settings-2" class="header-icon"></i>
                <h2>읽기 설정</h2>
                <!-- lucide.createIcons()가 data-lucide 엘리먼트를 <svg>로
                     바꿔치기해 Vue의 vnode 추적과 어긋난다 — v-if/v-else로
                     아이콘을 통째로 스왑하면 다음 클릭 때 Vue가 이미 lucide가
                     치환해버린(사라진) 노드를 기준으로 insertBefore를 시도하다
                     크래시한다("Cannot read properties of null"). 대신 두
                     아이콘을 순수 SVG로 미리 그려두고 v-show(display만
                     토글, 노드 삽입/제거 없음)로 바꾼다 — 재생/일시정지
                     아이콘 토글과 같은 패턴. -->
                <svg v-show="isSettingsExpanded" class="profile-settings-toggle-chevron" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>
                <svg v-show="!isSettingsExpanded" class="profile-settings-toggle-chevron" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"/></svg>
            </button>
            <div class="profile-settings-collapse" :class="{ 'is-expanded': isSettingsExpanded }">
                <div class="profile-settings-collapse-inner">
                    <button class="myfiles-row" type="button" @click="themeLogic.openSheet">
                        <i data-lucide="palette" class="myfiles-row-icon"></i>
                        <span class="myfiles-row-title">읽기 화면 테마</span>
                        <span class="myfiles-row-value">{{ themeLabel }}</span>
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
                        <span class="myfiles-row-value">{{ speedLabel }}</span>
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
                </div>
            </div>
        </div>

        <div class="profile-spacer" aria-hidden="true"></div>
        <button v-if="authStore.isLoggedIn" type="button" class="profile-logout-btn" @click="openLogoutConfirm">
            <i data-lucide="log-out"></i>
            로그아웃
        </button>
    </main>

    <div class="action-sheet-backdrop" :class="{ show: isLogoutConfirmOpen }" role="dialog" aria-modal="true" aria-label="로그아웃" @click="onLogoutBackdropClick">
        <div class="action-sheet">
            <div class="action-sheet-handle"></div>
            <div class="login-prompt-body">
                <p class="login-prompt-title">로그아웃하시겠습니까?</p>
                <p class="login-prompt-desc">현재 재생은 중지되며, 다시 로그인하면 저장된 파일을 계속 사용할 수 있어요.</p>
            </div>
            <button type="button" class="action-sheet-btn action-sheet-btn-danger" @click="confirmLogout">로그아웃</button>
            <button type="button" class="action-sheet-btn action-sheet-btn-cancel" @click="closeLogoutConfirm">취소</button>
        </div>
    </div>
</template>
