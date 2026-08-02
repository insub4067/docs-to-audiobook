<script setup lang="ts">
import { computed, onMounted, onUnmounted, watch, type ComponentPublicInstance } from "vue";
import { useAuthStore } from "../../stores/auth";
import { useAuthLogic } from "../../composables/Auth/Auth_Logic.vue";
import { useHeaderState } from "./Header_State.vue";
import { useHeaderLogic } from "./Header_Logic.vue";

const authStore = useAuthStore();
const authLogic = useAuthLogic();
const { isProfileMenuOpen, authError, googleButtonSlots } = useHeaderState();
const { toggleProfileMenu, closeProfileMenu, handleLogout, handleLogoTap, setupSocialLogin } =
    useHeaderLogic({ isProfileMenuOpen, authError, googleButtonSlots });

const profileName = computed(() => authStore.user?.full_name || authStore.user?.email || "사용자");
const profileInitial = computed(() => profileName.value.trim().split(/\s+/)[0].slice(0, 2));

function registerGoogleSlot(el: Element | ComponentPublicInstance | null) {
    if (!el || !(el instanceof HTMLElement)) return;
    const list = googleButtonSlots.value;
    if (!list.includes(el)) list.push(el);
}

watch(() => authStore.isLoggedIn, (loggedIn) => {
    if (!loggedIn) setupSocialLogin();
});

onMounted(async () => {
    await authLogic.initializeAuth();
    if (!authStore.isLoggedIn) await setupSocialLogin();
    document.addEventListener("click", closeProfileMenu);
    document.addEventListener("keydown", handleEscape);
});

function handleEscape(event: KeyboardEvent) {
    if (event.key === "Escape") isProfileMenuOpen.value = false;
}

onUnmounted(() => {
    document.removeEventListener("click", closeProfileMenu);
    document.removeEventListener("keydown", handleEscape);
});
</script>

<template>
    <header class="app-header">
        <div class="header-left">
            <div class="logo">
                <h1 class="brand-wordmark" :data-admin="authStore.isAdmin" @click="handleLogoTap">TEXTAUDIO</h1>
            </div>
        </div>

        <div class="user-info" id="userInfo" :style="{ display: authStore.isLoggedIn ? 'flex' : 'none' }">
            <button
                class="profile-trigger"
                type="button"
                :aria-label="`${profileName} 계정 메뉴`"
                aria-haspopup="menu"
                :aria-expanded="isProfileMenuOpen"
                aria-controls="profileMenu"
                @click="toggleProfileMenu"
            >
                <img id="profileImage" alt="" hidden>
                <span id="profileInitial" aria-hidden="true">{{ profileInitial }}</span>
            </button>
            <div class="profile-menu" id="profileMenu" role="menu" :hidden="!isProfileMenuOpen">
                <p class="profile-email" id="userEmail">{{ authStore.user?.email || "" }}</p>
                <a
                    class="profile-menu-link"
                    id="adminDashboardLink"
                    href="/admin"
                    role="menuitem"
                    :hidden="!authStore.isAdmin"
                >
                    <i data-lucide="layout-dashboard"></i>
                    관리자 페이지
                </a>
                <button class="btn-logout" id="logoutBtn" type="button" role="menuitem" aria-label="로그아웃" @click="handleLogout">
                    <i data-lucide="log-out"></i>
                    로그아웃
                </button>
            </div>
        </div>

        <div class="header-login" id="headerLoginSlot" :style="{ display: authStore.isLoggedIn ? 'none' : 'flex' }">
            <div id="headerGoogleBtn" :ref="registerGoogleSlot"></div>
        </div>
    </header>

    <section class="auth-container" id="authContainer" style="display: none;">
        <div class="glass-card auth-card">
            <div class="auth-header">
                <h2>TextAudio 시작하기</h2>
                <p>Google 계정으로 쉽게 가입 및 로그인하세요</p>
            </div>
            <div id="googleLoginBtn" :ref="registerGoogleSlot"></div>
            <p class="auth-message" :class="{ error: authError }">{{ authError }}</p>
        </div>
    </section>
</template>
