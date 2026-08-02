import { defineStore } from 'pinia';
import { ref } from 'vue';

export const usePlayerStore = defineStore('player', () => {
  const currentAudiobook = ref<any | null>(null);
  const isPlaying = ref(false);
  const currentTime = ref(0);
  const duration = ref(0);
  const playbackSpeed = ref(1.0);
  const repeatMode = ref('off'); // 'off', 'one', 'all'
  const isReaderOpen = ref(false);
  
  function openReader(book: any) {
    currentAudiobook.value = book;
    isReaderOpen.value = true;
  }
  
  function closeReader() {
    isReaderOpen.value = false;
    currentAudiobook.value = null;
    isPlaying.value = false;
  }
  
  return {
    currentAudiobook,
    isPlaying,
    currentTime,
    duration,
    playbackSpeed,
    repeatMode,
    isReaderOpen,
    openReader,
    closeReader
  };
});
