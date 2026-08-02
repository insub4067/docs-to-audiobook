import { ref } from 'vue';

const isVisible = ref(false);
const message = ref('');
const type = ref('info'); // 'info', 'success', 'error'
let timeoutId: number | null = null;

export function useToast() {
  function showToast(msg: string, toastType: string = 'info', duration: number = 3000) {
    message.value = msg;
    type.value = toastType;
    isVisible.value = true;

    if (timeoutId !== null) {
      clearTimeout(timeoutId);
    }

    timeoutId = window.setTimeout(() => {
      isVisible.value = false;
    }, duration);
  }

  return {
    isVisible,
    message,
    type,
    showToast
  };
}
