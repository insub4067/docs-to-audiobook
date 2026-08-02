<script lang="ts">
import { ref, type Ref } from 'vue';

export interface GenerationState {
  previewText: Ref<string>;
  charCount: Ref<number>;
  selectedVoice: Ref<string>;
  voices: Ref<any[]>;
  speed: Ref<number>;
  pitch: Ref<number>;
  isGenerating: Ref<boolean>;
}

export function useGenerationState(): GenerationState {
  return {
    previewText: ref(''),
    charCount: ref(0),
    selectedVoice: ref(''),
    voices: ref([]),
    speed: ref(1.0),
    pitch: ref(0),
    isGenerating: ref(false)
  };
}

export default {};
</script>
