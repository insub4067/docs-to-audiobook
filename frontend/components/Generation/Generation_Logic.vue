<script lang="ts">
import type { GenerationState } from './Generation_State.vue';
import { useAuthStore } from '../../stores/auth';
import { useToast } from '../../composables/useToast';
import { useModal } from '../../composables/useModal';
import { computed, onMounted } from 'vue';

export interface GenerationLogic {
  loadVoices: () => Promise<void>;
  previewVoice: () => void;
  startGeneration: () => Promise<void>;
  speedLabel: import('vue').ComputedRef<string>;
  pitchLabel: import('vue').ComputedRef<string>;
  selectedVoiceDesc: import('vue').ComputedRef<string>;
}

export function useGenerationLogic({ 
  previewText, charCount, selectedVoice, voices, speed, pitch, isGenerating 
}: GenerationState): GenerationLogic {
  
  const authStore = useAuthStore();
  const toast = useToast();
  const modal = useModal();

  const speedLabel = computed(() => {
    if (speed.value < 0.8) return `느림 (${speed.value}x)`;
    if (speed.value > 1.2) return `빠름 (${speed.value}x)`;
    return `보통 (${speed.value}x)`;
  });

  const pitchLabel = computed(() => {
    if (pitch.value < -20) return `낮음 (${pitch.value}Hz)`;
    if (pitch.value > 20) return `높음 (${pitch.value}Hz)`;
    return `기본 (${pitch.value}Hz)`;
  });

  const selectedVoiceDesc = computed(() => {
    const voice = voices.value.find(v => v.id === selectedVoice.value);
    return voice ? voice.description : '음성 특징이 표시됩니다.';
  });

  async function loadVoices() {
    // Mock loading voices
    setTimeout(() => {
      voices.value = [
        { id: 'v1', name: '차분한 여성', description: '뉴스나 안내 방송에 어울리는 차분하고 명확한 목소리입니다.' },
        { id: 'v2', name: '활기찬 남성', description: '에너지가 넘치고 이야기 전달력이 좋은 목소리입니다.' }
      ];
      if (voices.value.length > 0) {
        selectedVoice.value = voices.value[0].id;
      }
    }, 300);
  }

  function previewVoice() {
    if (!selectedVoice.value) return;
    toast.showToast(`${selectedVoice.value} 목소리 미리듣기 재생 중...`, 'info');
    // Actual audio play logic...
  }

  async function startGeneration() {
    if (!authStore.user) {
      toast.showToast('Google 계정으로 로그인해야 오디오북을 만들 수 있어요.', 'error');
      return;
    }

    if (!selectedVoice.value) {
      toast.showToast('목소리를 선택해주세요.', 'error');
      return;
    }

    isGenerating.value = true;
    
    // Mock API call
    setTimeout(() => {
      isGenerating.value = false;
      modal.hide();
      toast.showToast('오디오북 생성이 완료되었습니다! 라이브러리를 확인하세요.', 'success');
      // Trigger library reload or emit event
    }, 3000);
  }

  onMounted(() => {
    loadVoices();
    // In a real scenario, previewText and charCount would be populated by props passed to the modal
    previewText.value = '문서에서 추출된 텍스트 내용이 여기에 표시됩니다. ...';
    charCount.value = previewText.value.length;
  });

  return {
    loadVoices,
    previewVoice,
    startGeneration,
    speedLabel,
    pitchLabel,
    selectedVoiceDesc
  };
}

export default {};
</script>
