<script setup lang="ts">
import { useLibraryState } from './Library_State.vue';
import { useLibraryLogic } from './Library_Logic.vue';
import { useLibraryStore } from '../../stores/library';
import { onUpdated } from 'vue';

const state = useLibraryState();
const logic = useLibraryLogic(state);
const libraryStore = useLibraryStore();

onUpdated(() => {
  if (typeof window !== 'undefined' && (window as any).lucide) {
    (window as any).lucide.createIcons();
  }
});
</script>

<template>
  <section class="glass-card library-section">
    <div class="card-header">
      <i data-lucide="folder-heart" class="header-icon"></i>
      <h2>내 오디오북</h2>
      <button 
        class="btn-icon" 
        aria-label="공유 링크 불러오기" 
        title="공유 링크 불러오기" 
        style="margin-left: auto; width: 44px; height: 44px; border-radius: 50%; background: var(--glass-bg); border: 1px solid var(--glass-border); display: flex; align-items: center; justify-content: center; cursor: pointer; color: var(--text-color); transition: all 0.3s ease;"
        @click="$emit('import-link')"
      >
        <i data-lucide="link" style="width: 18px; height: 18px;"></i>
      </button>
    </div>
    
    <div class="library-container">
      <div v-if="state.isLoading.value" style="text-align: center; padding: 2rem;">
        <div class="spinner-container" style="width: 32px; height: 32px; margin: 0 auto;">
          <div class="double-bounce1"></div>
          <div class="double-bounce2"></div>
        </div>
      </div>
      
      <div class="library-empty" v-else-if="libraryStore.audiobooks.length === 0">
        <i data-lucide="music"></i>
        <p>아직 생성된 책이 없습니다.</p>
        <span>새로운 문서를 업로드해 보세요.</span>
      </div>
      
      <div class="audio-list" v-else>
        <div 
          v-for="book in libraryStore.audiobooks" 
          :key="book.id"
          class="audio-item"
          :class="book.status"
          @click="logic.playAudiobook(book)"
        >
          <div class="audio-item-icon">
            <i :data-lucide="book.status === 'completed' ? 'headphones' : (book.status === 'failed' ? 'alert-circle' : 'loader')"></i>
          </div>
          <div class="audio-item-content">
            <h4 class="audio-item-title">{{ book.title }}</h4>
            <div class="audio-item-meta">
              <span>{{ logic.formatDate(book.created_at) }}</span>
              <span v-if="book.status === 'failed'" class="status-badge failed">생성 실패</span>
              <span v-else-if="book.status === 'generating'" class="status-badge generating">생성 중...</span>
            </div>
          </div>
          <button 
            class="audio-item-action" 
            @click.stop="logic.openOptions(book)"
            aria-label="옵션 보기"
          >
            <i data-lucide="more-vertical"></i>
          </button>
        </div>
      </div>
    </div>
  </section>
</template>
