<script lang="ts">
import { ref, type Ref } from 'vue';

export interface ReaderState {
  currentSentenceIndex: Ref<number>;
  sentences: Ref<any[]>;
  audioSrc: Ref<string | null>;
  showIndex: Ref<boolean>;
  showShare: Ref<boolean>;
}

export function useReaderState(): ReaderState {
  return {
    currentSentenceIndex: ref(-1),
    sentences: ref([]),
    audioSrc: ref(null),
    showIndex: ref(false),
    showShare: ref(false)
  };
}

export default {};
</script>
