<script lang="ts">
import { ref, type Ref } from 'vue';

export interface HomeState {
  isDragging: Ref<boolean>;
  isUploading: Ref<boolean>;
  urlInput: Ref<string>;
}

export function useHomeState(): HomeState {
  return {
    isDragging: ref(false),
    isUploading: ref(false),
    urlInput: ref('')
  };
}

export default {};
</script>
