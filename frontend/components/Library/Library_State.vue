<script lang="ts">
import { ref, type Ref } from 'vue';

export interface LibraryState {
  isLoading: Ref<boolean>;
  filterStatus: Ref<string>; // 'all', 'completed', 'failed'
}

export function useLibraryState(): LibraryState {
  return {
    isLoading: ref(false),
    filterStatus: ref('all')
  };
}

export default {};
</script>
