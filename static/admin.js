function formatMetric(name, value) {
    if (value === null || value === undefined) return "—";
    if (name.endsWith("_rate")) return `${value}%`;
    return Number(value).toLocaleString("ko-KR");
}

const metricDetails = {
    weekly_active_users: {
        title: "주간 활성 사용자",
        description: "최근 7일 안에 서비스 이벤트를 한 번 이상 기록한 고유 사용자 수입니다.",
        basis: "생성 시작·완료·실패와 첫 재생 이벤트를 기준으로 중복 없이 집계합니다.",
    },
    daily_active_users: {
        title: "일간 활성 사용자",
        description: "최근 24시간 안에 서비스 이벤트를 한 번 이상 기록한 고유 사용자 수입니다.",
        basis: "같은 사용자의 여러 행동은 한 명으로 집계합니다.",
    },
    week_one_retention_rate: {
        title: "1주 재방문율",
        description: "첫 이벤트 후 7~14일 사이 코호트 중, 다음 7일에도 다시 활동한 사용자의 비율입니다.",
        basis: "코호트가 아직 없으면 비율 대신 —로 표시합니다.",
    },
    total_users: {
        title: "전체 사용자",
        description: "가입한 전체 계정 수입니다.",
        basis: "보조 수치는 최근 7일 동안 새로 가입한 계정 수입니다.",
    },
    generation_success_rate: {
        title: "생성 성공률",
        description: "최근 30일 생성 완료 수를 완료와 실패의 합으로 나눈 비율입니다.",
        basis: "완료 또는 실패 이벤트가 아직 없으면 비율 대신 —로 표시합니다.",
    },
    playback_started_30d: {
        title: "첫 재생",
        description: "최근 30일 동안 오디오북 읽기 화면을 열어 재생을 시작한 횟수입니다.",
        basis: "고유 사용자 수가 아니라 시작 횟수이므로 같은 사용자가 여러 번 포함될 수 있습니다.",
    },
    total_audiobooks: {
        title: "보관함 오디오북",
        description: "사용자 보관함에 저장된 오디오북의 총 개수입니다.",
        basis: "보조 수치는 최근 30일 생성 실패 이벤트 수입니다.",
    },
};

let latestMetrics = {};
let metricDetailTrigger = null;

function renderMetricPeople(metricName) {
    const list = document.getElementById("metricDetailList");
    const people = latestMetrics.metric_details?.[metricName] || [];
    list.replaceChildren();
    if (!people.length) {
        const item = document.createElement("li");
        item.className = "metric-detail-empty";
        item.textContent = "현재 조건에 해당하는 사용자가 없습니다.";
        list.append(item);
        return;
    }
    people.forEach((person) => {
        const item = document.createElement("li");
        const identity = document.createElement("div");
        const name = document.createElement("strong");
        const email = document.createElement("span");
        const meta = document.createElement("span");
        name.textContent = person.name;
        email.textContent = person.email;
        meta.textContent = person.meta;
        meta.className = "metric-detail-meta";
        identity.append(name, email);
        item.append(identity, meta);
        list.append(item);
    });
}

function openMetricDetail(metricName, trigger) {
    const detail = metricDetails[metricName];
    if (!detail) return;
    metricDetailTrigger = trigger;
    document.getElementById("metricDetailTitle").textContent = detail.title;
    document.getElementById("metricDetailValue").textContent = formatMetric(metricName, latestMetrics[metricName]);
    document.getElementById("metricDetailDescription").textContent = detail.description;
    document.getElementById("metricDetailBasis").textContent = detail.basis;
    renderMetricPeople(metricName);
    document.getElementById("metricDetailBackdrop").hidden = false;
    document.getElementById("metricDetailSheet").hidden = false;
    document.body.classList.add("metric-detail-open");
    document.getElementById("closeMetricDetailBtn").focus();
}

function closeMetricDetail() {
    document.getElementById("metricDetailBackdrop").hidden = true;
    document.getElementById("metricDetailSheet").hidden = true;
    document.body.classList.remove("metric-detail-open");
    metricDetailTrigger?.focus();
}

function renderMetrics(metrics) {
    latestMetrics = metrics;
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
document.querySelectorAll("[data-metric-card]").forEach((card) => {
    card.addEventListener("click", () => openMetricDetail(card.dataset.metricCard, card));
});
document.getElementById("closeMetricDetailBtn").addEventListener("click", closeMetricDetail);
document.getElementById("metricDetailBackdrop").addEventListener("click", closeMetricDetail);
document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !document.getElementById("metricDetailSheet").hidden) closeMetricDetail();
});
loadMetrics();
