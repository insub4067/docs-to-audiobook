<script lang="ts">
import type { AdminState, AdminTab, JsonValidationResult, LibraryAdminItem } from "./Admin_State.vue";
import type { AdminMetricName } from "../types/adminDashboard";

export interface AdminLogic {
    formatMetric(name: AdminMetricName, value: number | null | undefined): string;
    loadMetrics(): Promise<void>;
    selectTab(tab: AdminTab): void;
    validateJson(raw: string): JsonValidationResult;
    submitNews(): Promise<void>;
    submitLibrary(): Promise<void>;
    loadLibraryItems(): Promise<void>;
    openStatusMenu(item: LibraryAdminItem): void;
    closeStatusMenu(): void;
    toggleLibraryStatus(item: LibraryAdminItem): Promise<void>;
}

// 상태를 인자로 받는다(직접 import하지 않음) — 그래야 이 로직만 따로
// 테스트하거나, 필요하면 다른 상태 인스턴스에도 재사용할 수 있다.
export function useAdminLogic(
    {
        status, contentVisible, metrics, activeAdminTab, newsInputText, newsStatus, newsSubmitting,
        libraryInputText, libraryStatus, librarySubmitting,
        libraryItems, libraryItemsStatus, libraryTogglingIds, statusMenuItem,
    }: AdminState
): AdminLogic {
    function formatMetric(name: AdminMetricName, value: number | null | undefined): string {
        if (value === null || value === undefined) return "—";
        if (name.endsWith("_rate")) return `${value}%`;
        return Number(value).toLocaleString("ko-KR");
    }

    function selectTab(tab: AdminTab): void {
        activeAdminTab.value = tab;
    }

    async function loadMetrics(): Promise<void> {
        const token = localStorage.getItem("authToken");
        if (!token) {
            status.value = "관리자만 접근할 수 있습니다.";
            return;
        }

        status.value = "지표를 불러오는 중입니다.";
        try {
            const response = await fetch("/api/admin/metrics", {
                headers: { "Authorization": `Bearer ${token}` },
                cache: "no-store",
            });
            if (response.status === 401 || response.status === 403) {
                status.value = "관리자만 접근할 수 있습니다.";
                contentVisible.value = false;
                return;
            }
            if (!response.ok) throw new Error("지표를 불러오지 못했습니다.");
            metrics.value = await response.json();
            contentVisible.value = true;
            status.value = `마지막 갱신 ${new Date().toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })}`;
        } catch (error) {
            console.error(error);
            status.value = "지표를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.";
            contentVisible.value = false;
        }
    }

    // 등록 전에 형식·필수 필드를 미리 확인한다 — 모바일에서 긴 JSON을
    // 손으로 붙여넣다 보면 title/content 누락이나 문법 오류가 흔한데,
    // 그걸 등록 요청을 보내기 전에(백엔드 왕복 없이) 바로 알려준다.
    function validateJson(raw: string): JsonValidationResult {
        const empty: JsonValidationResult = { isValid: false, itemCount: 0, previewTitles: [], errors: [] };
        const text = raw.trim();
        if (!text) return empty;

        let jsonText = text;
        if (jsonText.startsWith("```")) {
            jsonText = jsonText.replace(/^```[a-zA-Z]*\n?/, "").replace(/```\s*$/, "").trim();
        }

        let parsed: unknown;
        try {
            parsed = JSON.parse(jsonText);
        } catch (error) {
            return { ...empty, errors: [`JSON 문법 오류가 발생했습니다: ${(error as Error).message}`] };
        }

        if (!Array.isArray(parsed)) {
            return { ...empty, errors: ["배열([ ]) 형식이어야 합니다."] };
        }
        if (parsed.length === 0) {
            return { ...empty, errors: ["배열이 비어 있습니다."] };
        }

        const errors: string[] = [];
        const previewTitles: string[] = [];
        parsed.forEach((raw, index) => {
            const item = raw as Record<string, unknown> | null;
            const ordinal = `${index + 1}번째 항목`;
            if (typeof item !== "object" || item === null) {
                errors.push(`${ordinal}이 객체가 아닙니다.`);
                return;
            }
            if (typeof item.title !== "string" || !item.title.trim()) errors.push(`${ordinal}에 title 필드가 없습니다.`);
            if (typeof item.content !== "string" || !item.content.trim()) errors.push(`${ordinal}에 content 필드가 없습니다.`);
            previewTitles.push(typeof item.title === "string" && item.title.trim() ? item.title : `(제목 없음 #${index + 1})`);
        });

        return { isValid: errors.length === 0, itemCount: parsed.length, previewTitles, errors };
    }

    async function submitNews(): Promise<void> {
        const token = localStorage.getItem("authToken");
        if (!token) {
            newsStatus.value = "관리자만 등록할 수 있습니다.";
            return;
        }
        const text = newsInputText.value.trim();
        if (!text) {
            newsStatus.value = "등록할 JSON을 입력해 주세요.";
            return;
        }

        newsSubmitting.value = true;
        newsStatus.value = "등록 요청 중입니다...";
        try {
            const response = await fetch("/api/admin/news", {
                method: "POST",
                headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
                body: JSON.stringify({ text }),
            });
            if (!response.ok) {
                const body = await response.json().catch(() => ({}));
                throw new Error(body.detail || "등록에 실패했습니다.");
            }
            const data = await response.json();
            const queuedCount = data.queued || 0;
            newsStatus.value = `${queuedCount}개 접수됨 — 변환이 끝나면 전체 사용자에게 알림이 발송돼요.`;
            newsInputText.value = "";
        } catch (error) {
            console.error(error);
            newsStatus.value = (error as Error).message || "등록에 실패했습니다.";
        } finally {
            newsSubmitting.value = false;
        }
    }

    async function submitLibrary(): Promise<void> {
        const token = localStorage.getItem("authToken");
        if (!token) {
            libraryStatus.value = "관리자만 등록할 수 있습니다.";
            return;
        }
        const text = libraryInputText.value.trim();
        if (!text) {
            libraryStatus.value = "등록할 JSON을 입력해 주세요.";
            return;
        }

        librarySubmitting.value = true;
        libraryStatus.value = "등록 요청 중입니다...";
        try {
            const response = await fetch("/api/admin/library", {
                method: "POST",
                headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
                body: JSON.stringify({ text }),
            });
            if (!response.ok) {
                const body = await response.json().catch(() => ({}));
                throw new Error(body.detail || "등록에 실패했습니다.");
            }
            const data = await response.json();
            const queuedCount = data.queued || 0;
            libraryStatus.value = `${queuedCount}개 접수됨 — status를 "published"로 명시하지 않은 작품은 검토 상태로만 저장되고 공개되지 않아요.`;
            libraryInputText.value = "";
            loadLibraryItems();
        } catch (error) {
            console.error(error);
            libraryStatus.value = (error as Error).message || "등록에 실패했습니다.";
        } finally {
            librarySubmitting.value = false;
        }
    }

    async function loadLibraryItems(): Promise<void> {
        const token = localStorage.getItem("authToken");
        if (!token) return;

        libraryItemsStatus.value = "작품 목록을 불러오는 중입니다.";
        try {
            const response = await fetch("/api/admin/library", {
                headers: { "Authorization": `Bearer ${token}` },
                cache: "no-store",
            });
            if (!response.ok) throw new Error("작품 목록을 불러오지 못했습니다.");
            const data = await response.json();
            libraryItems.value = data.items || [];
            libraryItemsStatus.value = "";
        } catch (error) {
            console.error(error);
            libraryItemsStatus.value = "작품 목록을 불러오지 못했습니다.";
        }
    }

    function openStatusMenu(item: LibraryAdminItem): void {
        statusMenuItem.value = item;
    }

    function closeStatusMenu(): void {
        statusMenuItem.value = null;
    }

    async function toggleLibraryStatus(item: LibraryAdminItem): Promise<void> {
        const token = localStorage.getItem("authToken");
        if (!token) return;
        const nextStatus = item.library_status === "published" ? "review" : "published";

        closeStatusMenu();
        libraryTogglingIds.value = new Set(libraryTogglingIds.value).add(item.id);
        try {
            const response = await fetch(`/api/admin/library/${item.id}`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
                body: JSON.stringify({ status: nextStatus }),
            });
            if (!response.ok) throw new Error("상태를 변경하지 못했습니다.");
            item.library_status = nextStatus;
        } catch (error) {
            console.error(error);
            libraryItemsStatus.value = (error as Error).message || "상태를 변경하지 못했습니다.";
        } finally {
            const next = new Set(libraryTogglingIds.value);
            next.delete(item.id);
            libraryTogglingIds.value = next;
        }
    }

    return {
        formatMetric, loadMetrics, selectTab, validateJson, submitNews, submitLibrary,
        loadLibraryItems, openStatusMenu, closeStatusMenu, toggleLibraryStatus,
    };
}

// 이 파일은 템플릿 없는 "로직 전용" 컴포넌트라, Vue SFC 컴파일러가 요구하는
// 기본 export 자리만 채운다. 실제로 쓰이는 건 위 named export뿐이다.
export default {};
</script>
