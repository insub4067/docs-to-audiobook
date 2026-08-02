<template>
  <Teleport to="body">
    <div 
      v-if="state.isVisible" 
      class="action-sheet-backdrop" 
      role="dialog" 
      aria-modal="true" 
      @click="hide"
    >
      <div class="action-sheet" @click.stop>
        <div class="action-sheet-handle"></div>
        <div v-if="state.title" class="action-sheet-header">
          <h3>{{ state.title }}</h3>
        </div>
        
        <button 
          v-for="(option, index) in state.options" 
          :key="index"
          class="action-sheet-btn"
          :class="{ 'action-sheet-btn-danger': option.isDanger }"
          @click="handleOptionClick(option)"
        >
          <i v-if="option.icon" :data-lucide="option.icon"></i>
          {{ option.label }}
        </button>
        
        <button class="action-sheet-btn action-sheet-btn-cancel" @click="hide">닫기</button>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { onUpdated } from 'vue';
import { useActionSheet, type ActionSheetOption } from '../../composables/useActionSheet';

const { state, hide } = useActionSheet();

async function handleOptionClick(option: ActionSheetOption) {
  hide();
  await option.action();
}

onUpdated(() => {
  if (state.value.isVisible && typeof window !== 'undefined' && (window as any).lucide) {
    (window as any).lucide.createIcons();
  }
});
</script>
