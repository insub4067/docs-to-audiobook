<script lang="ts">
import type { HeaderState } from './Header_State.vue';
import { useAuthStore } from '../../stores/auth';
import { useToast } from '../../composables/useToast';
import { onMounted, onUnmounted } from 'vue';

export interface HeaderLogic {
  toggleProfileMenu: () => void;
  closeProfileMenu: (e: MouseEvent) => void;
  handleLogout: () => void;
  handlePushToggle: () => Promise<void>;
  initGoogleAuth: () => void;
}

export function useHeaderLogic({ isProfileMenuOpen, pushNotificationLabel, hasPushPermission }: HeaderState): HeaderLogic {
  const authStore = useAuthStore();
  const toast = useToast();

  function toggleProfileMenu() {
    isProfileMenuOpen.value = !isProfileMenuOpen.value;
  }

  function closeProfileMenu(e: MouseEvent) {
    const target = e.target as HTMLElement;
    if (isProfileMenuOpen.value && !target.closest('.user-info')) {
      isProfileMenuOpen.value = false;
    }
  }

  function handleLogout() {
    authStore.logout();
    isProfileMenuOpen.value = false;
    toast.showToast('로그아웃 되었습니다.', 'info');
  }

  async function handlePushToggle() {
    // Push notification logic placeholder
    toast.showToast('푸시 알림 기능은 준비 중입니다.', 'info');
  }

  function handleCredentialResponse(response: any) {
    // This will be implemented fully when we migrate auth.js
    console.log("Encoded JWT ID token: " + response.credential);
    // Send to backend...
  }

  function initGoogleAuth() {
    // In a real scenario, this is called when the GSI library loads.
    const clientId = (window as any).TA_CONFIG?.google_client_id;
    if (!clientId || !(window as any).google) return;

    (window as any).google.accounts.id.initialize({
      client_id: clientId,
      callback: handleCredentialResponse,
      auto_select: true
    });

    const btnSlot = document.getElementById('headerGoogleBtn');
    if (btnSlot) {
      (window as any).google.accounts.id.renderButton(btnSlot, {
        theme: 'outline',
        size: 'medium',
        type: 'standard',
        shape: 'pill',
        text: 'signin_with',
        logo_alignment: 'left'
      });
    }
  }

  onMounted(() => {
    document.addEventListener('click', closeProfileMenu);
  });

  onUnmounted(() => {
    document.removeEventListener('click', closeProfileMenu);
  });

  return {
    toggleProfileMenu,
    closeProfileMenu,
    handleLogout,
    handlePushToggle,
    initGoogleAuth
  };
}

export default {};
</script>
