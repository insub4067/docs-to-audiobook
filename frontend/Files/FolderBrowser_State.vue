<script lang="ts">
import { ref, type Ref } from "vue";

export interface FolderNode {
    id: string;
    name: string;
    parent_folder_id: string | null;
}

export interface BreadcrumbEntry {
    id: string | null;
    name: string;
}

export interface FolderBrowserState {
    currentFolderId: Ref<string | null>;
    breadcrumb: Ref<BreadcrumbEntry[]>;
    subfolders: Ref<FolderNode[]>;
    isLoading: Ref<boolean>;
}

export function useFolderBrowserState(rootLabel: string): FolderBrowserState {
    return {
        currentFolderId: ref(null),
        breadcrumb: ref([{ id: null, name: rootLabel }]),
        subfolders: ref([]),
        isLoading: ref(false),
    };
}

export default {};
</script>
