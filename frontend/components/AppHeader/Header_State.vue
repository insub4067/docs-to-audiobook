<script lang="ts">
import { ref, type Ref } from "vue";

export interface HeaderState {
    isProfileMenuOpen: Ref<boolean>;
    authError: Ref<string>;
    googleButtonSlots: Ref<Array<HTMLElement | null>>;
}

export function useHeaderState(): HeaderState {
    return {
        isProfileMenuOpen: ref(false),
        authError: ref(""),
        googleButtonSlots: ref([]),
    };
}

export default {};
</script>
