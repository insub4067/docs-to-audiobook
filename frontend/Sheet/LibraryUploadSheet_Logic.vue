<script lang="ts">
import type { LibraryUploadSheetState } from "./LibraryUploadSheet_State.vue";
import { useAuthLogic } from "../Auth/Auth_Logic.vue";
import { useToastLogic } from "../components/Toast/Toast_Logic.vue";
import { useToastState } from "../components/Toast/Toast_State.vue";

export interface LibraryUploadSheetLogic {
    open(): void;
    close(): void;
    submit(): Promise<void>;
}

export function useLibraryUploadSheetLogic(state: LibraryUploadSheetState): LibraryUploadSheetLogic {
    const authLogic = useAuthLogic();
    const { showToast } = useToastLogic(useToastState());

    function open(): void {
        state.status.value = "";
        state.isOpen.value = true;
    }

    function close(): void {
        state.isOpen.value = false;
    }

    async function submit(): Promise<void> {
        const text = state.text.value.trim();
        if (!text) {
            state.status.value = "등록할 JSON을 입력해 주세요.";
            return;
        }

        state.submitting.value = true;
        state.status.value = "등록 중입니다...";
        try {
            const response = await fetch("/api/admin/library", {
                method: "POST",
                headers: { ...authLogic.authHeaders(), "Content-Type": "application/json" },
                body: JSON.stringify({ text }),
            });
            if (!response.ok) {
                const body = await response.json().catch(() => ({}));
                throw new Error(body.detail || "등록에 실패했습니다.");
            }
            const data = await response.json();
            const queuedCount = data.queued || 0;
            state.status.value = `${queuedCount}개 접수됨 — status를 "published"로 명시하지 않으면 검토 상태로만 저장돼요.`;
            state.text.value = "";
            showToast(`라이브러리 작품 ${queuedCount}개를 접수했어요`, "success");
        } catch (error) {
            console.error(error);
            state.status.value = (error as Error).message || "등록에 실패했습니다.";
        } finally {
            state.submitting.value = false;
        }
    }

    return { open, close, submit };
}

export default {};
</script>
