import { defineStore } from 'pinia';
import { ref } from 'vue';

export interface User {
  id: string;
  email: string;
  fullName: string;
  avatarUrl: string | null;
  isAdmin: boolean;
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null);
  const isLoading = ref(true);

  function setUser(newUser: User | null) {
    user.value = newUser;
  }

  function setLoading(loading: boolean) {
    isLoading.value = loading;
  }
  
  function getAuthHeaders() {
    const token = localStorage.getItem('textAudio_authToken');
    return token ? { Authorization: `Bearer ${token}` } : {};
  }

  function logout() {
    localStorage.removeItem('textAudio_authToken');
    localStorage.removeItem('textAudio_userInfo');
    user.value = null;
    // PWA unsub/reload logic can be handled in a composable or component
  }

  return {
    user,
    isLoading,
    setUser,
    setLoading,
    getAuthHeaders,
    logout
  };
});
