<script setup lang="ts">
import { useReaderState } from './Reader_State.vue';
import { useReaderLogic } from './Reader_Logic.vue';
import { usePlayerStore } from '../../stores/player';
import { computed } from 'vue';

const playerStore = usePlayerStore();
const state = useReaderState();
const logic = useReaderLogic(state);

const progressPercent = computed(() => {
  if (playerStore.duration === 0) return 0;
  return (playerStore.currentTime / playerStore.duration) * 100;
});
</script>

<template>
  <div 
    v-if="playerStore.isReaderOpen"
    class="reader-overlay" 
    role="dialog" 
    aria-modal="true" 
    aria-label="오디오북 듣기"
  >
    <div class="reader-container">
      <header class="reader-header">
        <h3 class="reader-book-title">{{ playerStore.currentAudiobook?.title || '제목 없음' }}</h3>
        <div class="reader-header-actions" style="display: flex; gap: 8px;">
          <button class="btn-reader-close" aria-label="목차 보기" title="목차 보기" type="button" @click="state.showIndex.value = true">
            <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="8" y1="6" x2="21" y2="6"></line><line x1="8" y1="12" x2="21" y2="12"></line><line x1="8" y1="18" x2="21" y2="18"></line><line x1="3" y1="6" x2="3.01" y2="6"></line><line x1="3" y1="12" x2="3.01" y2="12"></line><line x1="3" y1="18" x2="3.01" y2="18"></line></svg>
          </button>
          <button class="btn-reader-close" aria-label="오디오북 듣기 닫기" title="오디오북 듣기 닫기" type="button" @click="logic.closeReader">
            <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
          </button>
        </div>
      </header>
      
      <div class="reader-content">
        <!-- Mock sentences render -->
        <p v-for="(sentence, idx) in state.sentences.value" :key="idx" :class="{ 'highlight': state.currentSentenceIndex.value === idx }">
          {{ sentence.text }}
        </p>
        <p v-if="state.sentences.value.length === 0">내용을 불러오는 중입니다...</p>
      </div>

      <footer class="reader-controls">
        <audio id="readerAudio"></audio>
        <div class="reader-player-ui">
          <button class="btn-player-skip" aria-label="10초 뒤로" title="10초 뒤로" type="button" @click="logic.skipBackward">
            <i data-lucide="skip-back"></i>
          </button>
          <button class="btn-player-play" aria-label="재생 또는 일시정지" title="재생 또는 일시정지" type="button" @click="logic.togglePlay">
            <svg v-if="!playerStore.isPlaying" xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="currentColor" stroke="none"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
            <svg v-else xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="currentColor" stroke="none"><rect x="6" y="4" width="4" height="16"></rect><rect x="14" y="4" width="4" height="16"></rect></svg>
          </button>
          <button class="btn-player-skip" aria-label="10초 앞으로" title="10초 앞으로" type="button" @click="logic.skipForward">
            <i data-lucide="skip-forward"></i>
          </button>
          
          <div class="reader-progress-wrapper">
            <span class="player-time">{{ logic.formatTime(playerStore.currentTime) }}</span>
            <div class="player-progress-bar">
              <div class="player-progress-fill" :style="{ width: progressPercent + '%' }"></div>
            </div>
            <span class="player-time">{{ logic.formatTime(playerStore.duration) }}</span>
          </div>
        </div>
      </footer>
    </div>
  </div>
</template>
