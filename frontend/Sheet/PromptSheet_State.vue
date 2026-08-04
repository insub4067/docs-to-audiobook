<script lang="ts">
import { ref, type Ref } from "vue";

export interface PromptSheetState {
    isOpen: Ref<boolean>;
    title: Ref<string>;
    subtitle: Ref<string>;
    value: Ref<string>;
    numeric: Ref<boolean>;
}

// Toast_State.vue와 같은 이유로 모듈 싱글턴이다 — window.prompt()를 대신하는
// 컴포넌트라 auth/library 로직 등 컴포넌트 바깥에서도 호출된다.
const state: PromptSheetState = {
    isOpen: ref(false),
    title: ref(""),
    subtitle: ref(""),
    value: ref(""),
    numeric: ref(false),
};

export function usePromptSheetState(): PromptSheetState {
    return state;
}

export default {};
</script>
