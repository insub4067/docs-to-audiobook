function formatMetric(name, value) {
    if (value === null || value === undefined) return "—";
    if (name.endsWith("_rate")) return `${value}%`;
    return Number(value).toLocaleString("ko-KR");
}

function renderMetrics(metrics) {
    document.querySelectorAll("[data-metric]").forEach((element) => {
        const name = element.dataset.metric;
        element.textContent = formatMetric(name, metrics[name]);
    });
    const cohort = document.getElementById("retentionCohort");
    cohort.textContent = metrics.retention_cohort_size
        ? `${metrics.retention_cohort_size}명 코호트 기준`
        : "측정 코호트 없음";
}

async function loadMetrics() {
    const status = document.getElementById("dashboardStatus");
    const content = document.getElementById("dashboardContent");
    const token = localStorage.getItem("authToken");
    if (!token) {
        status.textContent = "관리자만 접근할 수 있습니다.";
        return;
    }

    status.textContent = "지표를 불러오는 중입니다.";
    try {
        const response = await fetch("/api/admin/metrics", {
            headers: { "Authorization": `Bearer ${token}` },
            cache: "no-store",
        });
        if (response.status === 401 || response.status === 403) {
            status.textContent = "관리자만 접근할 수 있습니다.";
            content.hidden = true;
            return;
        }
        if (!response.ok) throw new Error("지표를 불러오지 못했습니다.");
        renderMetrics(await response.json());
        content.hidden = false;
        status.textContent = `마지막 갱신 ${new Date().toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })}`;
    } catch (error) {
        console.error(error);
        status.textContent = "지표를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.";
        content.hidden = true;
    }
}

document.getElementById("refreshMetricsBtn").addEventListener("click", loadMetrics);
loadMetrics();
