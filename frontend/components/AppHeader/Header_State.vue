<script lang="ts">
import { ref, type Ref } from 'vue';

export interface HeaderState {
  isProfileMenuOpen: Ref<boolean>;
  pushNotificationLabel: Ref<string>;
  hasPushPermission: Ref<boolean>;
}

export function useHeaderState(): HeaderState {
  return {
    isProfileMenuOpen: ref(false),
    pushNotificationLabel: ref('알림 켜기'),
    hasPushPermission: ref(false)
  };
}

export default {};
</script>
