<script setup lang="ts">
import { useAuthStore } from '../../stores/auth';
import { useHeaderState } from './Header_State.vue';
import { useHeaderLogic } from './Header_Logic.vue';
import { onMounted } from 'vue';

const authStore = useAuthStore();
const state = useHeaderState();
const logic = useHeaderLogic(state);

onMounted(() => {
  // Give it a tiny delay to ensure the GSI script is loaded if it's placed in index.html
  setTimeout(() => {
    logic.initGoogleAuth();
  }, 500);
});
</script>

<template>
  <header class="app-header">
    <div class="header-left">
      <div class="logo">
        <h1 class="brand-wordmark">TEXTAUDIO</h1>
      </div>
    </div>

    <!-- User Info Section -->
    <div class="user-info" v-if="authStore.user">
      <button 
        class="profile-trigger" 
        type="button" 
        aria-label="계정 메뉴" 
        aria-haspopup="menu" 
        :aria-expanded="state.isProfileMenuOpen.value" 
        @click="logic.toggleProfileMenu"
      >
        <img v-if="authStore.user.avatarUrl" :src="authStore.user.avatarUrl" alt="">
        <span v-else aria-hidden="true">{{ authStore.user.fullName?.[0] || '?' }}</span>
      </button>
      
      <div class="profile-menu" role="menu" v-show="state.isProfileMenuOpen.value">
        <p class="profile-email">{{ authStore.user.email }}</p>
        <router-link v-if="authStore.user.isAdmin" class="profile-menu-link" to="/admin" role="menuitem">
          <i data-lucide="layout-dashboard"></i>
          관리자 페이지
        </router-link>
        <button class="profile-menu-link" type="button" role="menuitem" @click="logic.handlePushToggle">
          <i data-lucide="bell"></i>
          <span>{{ state.pushNotificationLabel.value }}</span>
        </button>
        <button class="btn-logout" type="button" role="menuitem" aria-label="로그아웃" @click="logic.handleLogout">
          <i data-lucide="log-out"></i>
          로그아웃
        </button>
      </div>
    </div>

    <!-- Login Section -->
    <div class="header-login" v-else>
      <div id="headerGoogleBtn"></div>
    </div>
  </header>
</template>
