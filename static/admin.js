const { createApp, ref, onMounted } = Vue;

createApp({
    setup() {
        const status = ref("지표를 불러오는 중입니다.");
        const contentVisible = ref(false);
        const metrics = ref({});

        function formatMetric(name, value) {
            if (value === null || value === undefined) return "—";
            if (name.endsWith("_rate")) return `${value}%`;
            return Number(value).toLocaleString("ko-KR");
        }

        async function loadMetrics() {
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

        onMounted(loadMetrics);

        return { status, contentVisible, metrics, formatMetric, loadMetrics };
    },
}).mount("#dashboardApp");
