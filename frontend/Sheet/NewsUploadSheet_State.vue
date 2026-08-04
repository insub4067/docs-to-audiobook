<script lang="ts">
import { ref, type Ref } from "vue";

export interface NewsUploadSheetState {
    isOpen: Ref<boolean>;
    text: Ref<string>;
    status: Ref<string>;
    submitting: Ref<boolean>;
}

const state: NewsUploadSheetState = {
    isOpen: ref(false),
    text: ref(""),
    status: ref(""),
    submitting: ref(false),
};

export function useNewsUploadSheetState(): NewsUploadSheetState {
    return state;
}

export default {};
</script>
