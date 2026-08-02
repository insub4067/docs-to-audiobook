<script lang="ts">
import type { ReaderState } from './Reader_State.vue';
import { usePlayerStore } from '../../stores/player';
import { useToast } from '../../composables/useToast';
import { watch, onMounted, onUnmounted } from 'vue';

export interface ReaderLogic {
  togglePlay: () => void;
  skipForward: () => void;
  skipBackward: () => void;
  closeReader: () => void;
  formatTime: (time: number) => string;
}

export function useReaderLogic({ currentSentenceIndex, sentences, audioSrc }: ReaderState): ReaderLogic {
  const playerStore = usePlayerStore();
  const toast = useToast();
  let audioEl: HTMLAudioElement | null = null;

  function togglePlay() {
    playerStore.isPlaying = !playerStore.isPlaying;
    if (playerStore.isPlaying) {
      audioEl?.play();
    } else {
      audioEl?.pause();
    }
  }

  function skipForward() {
    if (audioEl) audioEl.currentTime += 10;
  }

  function skipBackward() {
    if (audioEl) audioEl.currentTime -= 10;
  }

  function closeReader() {
    if (audioEl) {
      audioEl.pause();
      audioEl.src = '';
    }
    playerStore.closeReader();
  }

  function formatTime(time: number) {
    if (isNaN(time)) return '00:00';
    const min = Math.floor(time / 60);
    const sec = Math.floor(time % 60);
    return `${min.toString().padStart(2, '0')}:${sec.toString().padStart(2, '0')}`;
  }

  function setupAudio() {
    audioEl = document.getElementById('readerAudio') as HTMLAudioElement;
    if (!audioEl) return;

    audioEl.addEventListener('timeupdate', () => {
      playerStore.currentTime = audioEl!.currentTime;
    });

    audioEl.addEventListener('loadedmetadata', () => {
      playerStore.duration = audioEl!.duration;
    });

    audioEl.addEventListener('ended', () => {
      playerStore.isPlaying = false;
      if (playerStore.repeatMode === 'one') {
        audioEl!.currentTime = 0;
        audioEl!.play();
      } else if (playerStore.repeatMode === 'all') {
        // Handle playlist repeat logic later
      }
    });
  }

  watch(() => playerStore.currentAudiobook, (book) => {
    if (book) {
      // Mock loading logic
      sentences.value = book.sentences || [];
      if (book.audioData) {
        const blob = new Blob([book.audioData], { type: 'audio/mp3' });
        audioSrc.value = URL.createObjectURL(blob);
      } else if (book.cloudUrl) {
        audioSrc.value = book.cloudUrl;
      }
      
      if (audioSrc.value && audioEl) {
        audioEl.src = audioSrc.value;
        audioEl.play();
        playerStore.isPlaying = true;
      }
    }
  });

  onMounted(() => {
    setupAudio();
  });

  onUnmounted(() => {
    if (audioEl) {
      audioEl.pause();
      audioEl.src = '';
    }
  });

  return {
    togglePlay,
    skipForward,
    skipBackward,
    closeReader,
    formatTime
  };
}

export default {};
</script>
