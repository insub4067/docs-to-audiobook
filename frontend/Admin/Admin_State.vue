<script lang="ts">
import { ref, type Ref } from "vue";
import type { AdminMetrics } from "../types/adminDashboard";

export type AdminTab = "dashboard" | "create" | "publishing";

export interface LibraryAdminItem {
    id: string;
    title: string;
    library_status: "review" | "published";
    library_category: string | null;
    library_edition: string | null;
    library_translator: string | null;
    library_source: string | null;
    library_rights: string | null;
    library_description: string | null;
    created_at: string;
}

/** 편집 시트에서 고칠 수 있는 서지 정보. 본문(오디오)은 여기서 못 바꾼다. */
export interface LibraryEditDraft {
    title: string;
    category: string;
    edition: string;
    translator: string;
    source: string;
    rights: string;
    description: string;
}

/** 합성이 끝나기 전(또는 실패한) 등록 작업. 뉴스와 라이브러리가 같은
 *  테이블을 쓰므로 kind로 구분한다. 성공하면 목록에서 사라진다. */
export interface ContentJob {
    id: string;
    kind: "news" | "library";
    title: string;
    status: "queued" | "processing" | "error";
    error: string | null;
    progress: number | null;
    created_at: string;
}

export interface JsonValidationResult {
    isValid: boolean;
    itemCount: number;
    previewTitles: string[];
    errors: string[];
}

export interface AdminState {
    status: Ref<string>;
    contentVisible: Ref<boolean>;
    metrics: Ref<AdminMetrics>;
    activeAdminTab: Ref<AdminTab>;
    newsInputText: Ref<string>;
    newsStatus: Ref<string>;
    newsSubmitting: Ref<boolean>;
    libraryInputText: Ref<string>;
    libraryStatus: Ref<string>;
    librarySubmitting: Ref<boolean>;
    libraryItems: Ref<LibraryAdminItem[]>;
    libraryItemsStatus: Ref<string>;
    libraryTogglingIds: Ref<Set<string>>;
    contentJobs: Ref<ContentJob[]>;
    contentJobsStatus: Ref<string>;
    contentJobBusyIds: Ref<Set<string>>;
    statusMenuItem: Ref<LibraryAdminItem | null>;
    editingItem: Ref<LibraryAdminItem | null>;
    editDraft: Ref<LibraryEditDraft>;
    editSaving: Ref<boolean>;
    activeInputSheet: Ref<"news" | "library" | null>;
}

export function useAdminState(): AdminState {
    return {
        status: ref("지표를 불러오는 중입니다."),
        contentVisible: ref(false),
        metrics: ref({}),
        activeAdminTab: ref("dashboard"),
        newsInputText: ref(""),
        newsStatus: ref(""),
        newsSubmitting: ref(false),
        libraryInputText: ref(""),
        libraryStatus: ref(""),
        librarySubmitting: ref(false),
        libraryItems: ref([]),
        libraryItemsStatus: ref(""),
        libraryTogglingIds: ref(new Set()),
        contentJobs: ref([]),
        contentJobsStatus: ref(""),
        contentJobBusyIds: ref(new Set()),
        statusMenuItem: ref(null),
        editingItem: ref(null),
        editDraft: ref({ title: "", category: "", edition: "", translator: "", source: "", rights: "", description: "" }),
        editSaving: ref(false),
        activeInputSheet: ref(null),
    };
}

// 이 파일은 템플릿 없는 "상태 전용" 컴포넌트라, Vue SFC 컴파일러가 요구하는
// 기본 export 자리만 채운다. 실제로 쓰이는 건 위 named export뿐이다.
export default {};
</script>
