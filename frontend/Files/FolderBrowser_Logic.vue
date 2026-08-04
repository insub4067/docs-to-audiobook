<script lang="ts">
import { useAuthLogic } from "../Auth/Auth_Logic.vue";
import { useToastLogic } from "../components/Toast/Toast_Logic.vue";
import { useToastState } from "../components/Toast/Toast_State.vue";
import type { FolderBrowserState, FolderNode } from "./FolderBrowser_State.vue";

export interface FolderBrowserLogic {
    loadCurrentFolder(): Promise<void>;
    openFolder(folder: FolderNode): Promise<void>;
    goToBreadcrumb(index: number): Promise<void>;
    createFolder(name: string): Promise<void>;
    renameFolder(folder: FolderNode, name: string): Promise<void>;
    deleteFolder(folder: FolderNode): Promise<void>;
}

// 폴더는 오프라인 재생이 필요 없어 IndexedDB에 두지 않고, 화면에 들어올
// 때마다 /api/folders에서 바로 불러온다(로그인 필요). Files/MyFiles_View와
// Sheet/MoveToFolderSheet_View가 각자 독립된 인스턴스로 이 컴포저블을 쓴다
// (탐색 스택이 서로 달라야 하므로).
export function useFolderBrowserLogic(state: FolderBrowserState): FolderBrowserLogic {
    const authLogic = useAuthLogic();
    const { showToast } = useToastLogic(useToastState());

    async function loadCurrentFolder(): Promise<void> {
        if (!authLogic.isLoggedIn()) {
            state.subfolders.value = [];
            return;
        }
        state.isLoading.value = true;
        try {
            const query = state.currentFolderId.value ? `?parent_id=${state.currentFolderId.value}` : "";
            const res = await fetch(`/api/folders${query}`, { headers: authLogic.authHeaders() });
            if (!res.ok) throw new Error("폴더를 불러오지 못했습니다.");
            const data = await res.json();
            state.subfolders.value = data.folders || [];
        } catch (error) {
            console.error(error);
            showToast("폴더를 불러오지 못했습니다.", "error");
        } finally {
            state.isLoading.value = false;
        }
    }

    async function openFolder(folder: FolderNode): Promise<void> {
        state.currentFolderId.value = folder.id;
        state.breadcrumb.value = [...state.breadcrumb.value, { id: folder.id, name: folder.name }];
        // /api/folders 응답이 오기 전까지 이전 폴더의 하위 폴더 목록이
        // 화면에 그대로 남아 있던 버그 — 오디오북 목록은 이미 불러온
        // IndexedDB 데이터를 즉시 필터링해 맞게 보이는데, 폴더 목록만
        // 네트워크 응답을 기다리는 동안 stale 상태로 남았다.
        state.subfolders.value = [];
        await loadCurrentFolder();
    }

    async function goToBreadcrumb(index: number): Promise<void> {
        state.breadcrumb.value = state.breadcrumb.value.slice(0, index + 1);
        state.currentFolderId.value = state.breadcrumb.value[state.breadcrumb.value.length - 1].id;
        state.subfolders.value = [];
        await loadCurrentFolder();
    }

    async function createFolder(name: string): Promise<void> {
        const trimmed = name.trim();
        if (!trimmed) return;
        try {
            const res = await fetch("/api/folders", {
                method: "POST",
                headers: { ...authLogic.authHeaders(), "Content-Type": "application/json" },
                body: JSON.stringify({ name: trimmed, parent_folder_id: state.currentFolderId.value }),
            });
            if (!res.ok) throw new Error("폴더 생성 실패");
            await loadCurrentFolder();
        } catch (error) {
            console.error(error);
            showToast("폴더를 만들지 못했습니다.", "error");
        }
    }

    async function renameFolder(folder: FolderNode, name: string): Promise<void> {
        const trimmed = name.trim();
        if (!trimmed) return;
        try {
            const res = await fetch(`/api/folders/${folder.id}`, {
                method: "PATCH",
                headers: { ...authLogic.authHeaders(), "Content-Type": "application/json" },
                body: JSON.stringify({ name: trimmed }),
            });
            if (!res.ok) throw new Error("폴더 이름 변경 실패");
            await loadCurrentFolder();
        } catch (error) {
            console.error(error);
            showToast("폴더 이름을 바꾸지 못했습니다.", "error");
        }
    }

    async function deleteFolder(folder: FolderNode): Promise<void> {
        try {
            const res = await fetch(`/api/folders/${folder.id}`, {
                method: "DELETE",
                headers: authLogic.authHeaders(),
            });
            if (!res.ok) throw new Error("폴더 삭제 실패");
            await loadCurrentFolder();
        } catch (error) {
            console.error(error);
            showToast("폴더를 삭제하지 못했습니다.", "error");
        }
    }

    return { loadCurrentFolder, openFolder, goToBreadcrumb, createFolder, renameFolder, deleteFolder };
}

export default {};
</script>
