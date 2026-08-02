<script lang="ts">
import { ref, type Ref } from "vue";
import type { AdminMetrics } from "../types/adminDashboard";

export interface AdminDashboardState {
    status: Ref<string>;
    contentVisible: Ref<boolean>;
    metrics: Ref<AdminMetrics>;
}

export function useAdminDashboardState(): AdminDashboardState {
    return {
        status: ref("지표를 불러오는 중입니다."),
        contentVisible: ref(false),
        metrics: ref({}),
    };
}

// 이 파일은 템플릿 없는 "상태 전용" 컴포넌트라, Vue SFC 컴파일러가 요구하는
// 기본 export 자리만 채운다. 실제로 쓰이는 건 위 named export뿐이다.
export default {};
</script>
