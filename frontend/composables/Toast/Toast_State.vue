<script lang="ts">
import { ref, type Ref } from "vue";

export interface ToastState {
    message: Ref<string>;
    type: Ref<"info" | "success" | "error">;
    visible: Ref<boolean>;
    isTop: Ref<boolean>;
}

// static/js/toast.js의 toastTimeout/toast.className 등은 전부 이 모듈
// 하나의 싱글턴 상태로 대체한다(여러 컴포넌트가 showToast()를 호출해도
// 같은 토스트 하나를 공유해야 하므로, 매번 새 ref를 만들면 안 된다).
const state: ToastState = {
    message: ref(""),
    type: ref("info"),
    visible: ref(false),
    isTop: ref(false),
};

export function useToastState(): ToastState {
    return state;
}

export default {};
</script>
