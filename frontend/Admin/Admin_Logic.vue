<script lang="ts">
import type { AdminState } from "./Admin_State.vue";
import type { AdminMetricName } from "../types/adminDashboard";

export interface AdminLogic {
    formatMetric(name: AdminMetricName, value: number | null | undefined): string;
    loadMetrics(): Promise<void>;
    submitNews(): Promise<void>;
    submitLibrary(): Promise<void>;
}

// 상태를 인자로 받는다(직접 import하지 않음) — 그래야 이 로직만 따로
// 테스트하거나, 필요하면 다른 상태 인스턴스에도 재사용할 수 있다.
export function useAdminLogic(
    {
        status, contentVisible, metrics, newsInputText, newsStatus, newsSubmitting,
        libraryInputText, libraryStatus, librarySubmitting,
    }: AdminState
): AdminLogic {
    function formatMetric(name: AdminMetricName, value: number | null | undefined): string {
        if (value === null || value === undefined) return "—";
        if (name.endsWith("_rate")) return `${value}%`;
        return Number(value).toLocaleString("ko-KR");
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
        } catch (error) {
            console.error(error);
            libraryStatus.value = (error as Error).message || "등록에 실패했습니다.";
        } finally {
            librarySubmitting.value = false;
        }
    }

    return { formatMetric, loadMetrics, submitNews, submitLibrary };
}

// 이 파일은 템플릿 없는 "로직 전용" 컴포넌트라, Vue SFC 컴파일러가 요구하는
// 기본 export 자리만 채운다. 실제로 쓰이는 건 위 named export뿐이다.
export default {};
</script>
