<script lang="ts">
import type { PromptSheetState } from "./PromptSheet_State.vue";

export interface PromptSheetOptions {
    subtitle?: string;
    defaultValue?: string;
    numeric?: boolean;
}

export interface PromptSheetLogic {
    showPrompt(title: string, options?: PromptSheetOptions): Promise<string | null>;
    confirm(): void;
    cancel(): void;
}

// window.prompt()는 네이티브 다이얼로그라 iOS PWA에서 입력창이 자동
// 포커스되지 않는다 — 이 시트로 대신하면 열릴 때 확실히 포커스를 줄 수
// 있다. showPrompt()가 window.prompt()와 같은 형태(Promise<string|null>)를
// 돌려주므로 호출부는 `await`만 붙이면 된다.
let resolveCurrent: ((value: string | null) => void) | null = null;

export function usePromptSheetLogic(state: PromptSheetState): PromptSheetLogic {
    function showPrompt(title: string, options: PromptSheetOptions = {}): Promise<string | null> {
        // 이미 열려있는 프롬프트가 있으면(호출 실수 등) 취소로 정리하고 새로 연다.
        if (resolveCurrent) {
            resolveCurrent(null);
            resolveCurrent = null;
        }
        state.title.value = title;
        state.subtitle.value = options.subtitle || "";
        state.value.value = options.defaultValue || "";
        state.numeric.value = !!options.numeric;
        state.isOpen.value = true;
        return new Promise((resolve) => {
            resolveCurrent = resolve;
        });
    }

    function confirm(): void {
        state.isOpen.value = false;
        const value = state.value.value;
        resolveCurrent?.(value);
        resolveCurrent = null;
    }

    function cancel(): void {
        state.isOpen.value = false;
        resolveCurrent?.(null);
        resolveCurrent = null;
    }

    return { showPrompt, confirm, cancel };
}

export default {};
</script>
