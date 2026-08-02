<template>
  <Teleport to="body">
    <div 
      v-if="state.isVisible" 
      class="generation-modal" 
      style="display: flex; opacity: 1; pointer-events: auto;"
      role="dialog" 
      aria-modal="true" 
      @click="hide"
    >
      <div class="modal-content glass-card" @click.stop>
        <header class="modal-header">
          <h2>{{ state.title }}</h2>
          <button class="btn-icon" @click="hide" aria-label="닫기" title="닫기">
            <i data-lucide="x"></i>
          </button>
        </header>
        
        <!-- Slot for injecting components dynamically based on state.component -->
        <slot></slot>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { onUpdated } from 'vue';
import { useModal } from '../../composables/useModal';

const { state, hide } = useModal();

onUpdated(() => {
  if (state.value.isVisible && typeof window !== 'undefined' && (window as any).lucide) {
    (window as any).lucide.createIcons();
  }
});
</script>
