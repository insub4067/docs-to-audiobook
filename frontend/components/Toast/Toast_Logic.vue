<script lang="ts">
import type { ToastState } from "./Toast_State.vue";

export interface ToastLogic {
    showToast(message: string, type?: "info" | "success" | "error"): void;
    dismissToast(): void;
}

let toastTimeout: ReturnType<typeof setTimeout> | null = null;
// 리더 모드가 열려 있으면 토스트를 상단에 띄운다(static/js/toast.js와 동일
// 동작). Reader_Logic.vue의 open()/openSharedReaderMode()/closeReader()가
// 호출해 채워 넣는다.
let isReaderOpen = false;

export function setReaderOpenForToast(open: boolean): void {
    isReaderOpen = open;
}

export function useToastLogic({ message, type, visible, isTop }: ToastState): ToastLogic {
    function showToast(text: string, toastType: "info" | "success" | "error" = "info") {
        if (toastTimeout) clearTimeout(toastTimeout);

        message.value = text;
        type.value = toastType;
        isTop.value = isReaderOpen;
        visible.value = true;

        toastTimeout = setTimeout(() => {
            visible.value = false;
        }, 3500);
    }

    function dismissToast(): void {
        if (toastTimeout) clearTimeout(toastTimeout);
        visible.value = false;
    }

    return { showToast, dismissToast };
}

export default {};
</script>
