<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch, type ComponentPublicInstance } from "vue";
import { useAuthStore } from "../../stores/auth";
import { useAuthLogic } from "../../Auth/Auth_Logic.vue";
import { useHeaderState } from "./Header_State.vue";
import { useHeaderLogic } from "./Header_Logic.vue";
import { useNotificationsState } from "../../Notifications/Notifications_State.vue";
import { useNotificationsLogic } from "../../Notifications/Notifications_Logic.vue";
import type { ThemeLogic } from "../../Theme/Theme_Logic.vue";

const props = defineProps<{
    themeLogic: ThemeLogic;
    activeTab: "home" | "library" | "files";
}>();

const tabTitle = computed(() => {
    if (props.activeTab === "home") return "홈";
    if (props.activeTab === "library") return "라이브러리";
    return "내 파일";
});

const authStore = useAuthStore();
const authLogic = useAuthLogic();
const { isProfileMenuOpen, authError, googleButtonSlots } = useHeaderState();
const { toggleProfileMenu, closeProfileMenu, handleLogout, handleLogoTap, setupSocialLogin } =
    useHeaderLogic({ isProfileMenuOpen, authError, googleButtonSlots });
const notificationsState = useNotificationsState();
const notificationsLogic = useNotificationsLogic(notificationsState);

const pushNotificationLabel = computed(() => {
    if (notificationsState.pushState.value === "on") return "완료 알림 켜짐";
    if (notificationsState.pushState.value === "blocked") return "알림 차단됨";
    return "완료 알림 꺼짐";
});

const profileName = computed(() => authStore.user?.full_name || authStore.user?.email || "사용자");
const profileInitial = computed(() => profileName.value.trim().split(/\s+/)[0].slice(0, 2));

// 애플 네이티브 앱처럼 스크롤을 내리면 큰 타이틀이 작아지며 헤더에 배경/
// 경계선이 자연스럽게 나타나게 한다(.scrolled 클래스는 CSS 트랜지션으로
// 처리, 여기서는 임계값만 판단).
const isHeaderScrolled = ref(false);
function onWindowScroll(): void {
    isHeaderScrolled.value = window.scrollY > 8;
}

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
    await notificationsLogic.initialize();
    document.addEventListener("click", closeProfileMenu);
    document.addEventListener("keydown", handleEscape);
    window.addEventListener("scroll", onWindowScroll, { passive: true });
});

function openThemeSheet(): void {
    isProfileMenuOpen.value = false;
    props.themeLogic.openSheet();
}

function handleEscape(event: KeyboardEvent) {
    if (event.key === "Escape") isProfileMenuOpen.value = false;
}

onUnmounted(() => {
    document.removeEventListener("click", closeProfileMenu);
    document.removeEventListener("keydown", handleEscape);
    window.removeEventListener("scroll", onWindowScroll);
});
</script>

<template>
    <header class="app-header" :class="{ scrolled: isHeaderScrolled }">
        <div class="header-left">
            <div class="logo">
                <h1 class="page-title" :data-admin="authStore.isAdmin" @click="handleLogoTap">{{ tabTitle }}</h1>
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
                <button class="profile-menu-link" type="button" role="menuitem" @click="openThemeSheet">
                    <i data-lucide="palette"></i>
                    화면 테마
                </button>
                <button
                    class="profile-menu-link"
                    type="button"
                    role="menuitem"
                    :hidden="!notificationsState.isPushVisible.value"
                    :disabled="notificationsState.pushState.value === 'blocked'"
                    :aria-pressed="notificationsState.pushState.value === 'on'"
                    @click="notificationsLogic.togglePush"
                >
                    <i data-lucide="bell"></i>
                    <span>{{ pushNotificationLabel }}</span>
                </button>
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
