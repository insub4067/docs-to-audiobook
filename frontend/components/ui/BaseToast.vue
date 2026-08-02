<template>
  <Transition name="toast">
    <div v-if="isVisible" class="toast" role="status" aria-live="polite">
      <i :data-lucide="iconName"></i>
      <span>{{ message }}</span>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { computed, onUpdated } from 'vue';
import { useToast } from '../../composables/useToast';
import lucide from 'lucide';

const { isVisible, message, type } = useToast();

const iconName = computed(() => {
  if (type.value === 'success') return 'check-circle';
  if (type.value === 'error') return 'alert-circle';
  return 'info';
});

// Re-render lucide icons when toast becomes visible
onUpdated(() => {
  if (isVisible.value && typeof window !== 'undefined' && (window as any).lucide) {
    (window as any).lucide.createIcons();
  }
});
</script>

<style scoped>
.toast-enter-active,
.toast-leave-active {
  transition: all 0.3s ease;
}
.toast-enter-from {
  opacity: 0;
  transform: translate(-50%, 20px);
}
.toast-leave-to {
  opacity: 0;
  transform: translate(-50%, -20px);
}
</style>
