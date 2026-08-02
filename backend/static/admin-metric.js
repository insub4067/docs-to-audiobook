function formatMetric(name, value) {
    if (value === null || value === undefined) return "—";
    if (name.endsWith("_rate")) return `${value}%`;
    return Number(value).toLocaleString("ko-KR");
}

const metricDetails = {
    weekly_active_users: ["주간 활성 사용자", "최근 7일 안에 서비스 이벤트를 한 번 이상 기록한 고유 사용자 수입니다.", "생성 시작·완료·실패와 첫 재생 이벤트를 기준으로 중복 없이 집계합니다."],
    daily_active_users: ["일간 활성 사용자", "최근 24시간 안에 서비스 이벤트를 한 번 이상 기록한 고유 사용자 수입니다.", "같은 사용자의 여러 행동은 한 명으로 집계합니다."],
    week_one_retention_rate: ["1주 재방문율", "첫 이벤트 후 7~14일 사이 코호트 중, 다음 7일에도 다시 활동한 사용자의 비율입니다.", "코호트가 아직 없으면 비율 대신 —로 표시합니다."],
    total_users: ["전체 사용자", "가입한 전체 계정 수입니다.", "보조 수치는 최근 7일 동안 새로 가입한 계정 수입니다."],
    generation_success_rate: ["생성 성공률", "최근 30일 생성 완료 수를 완료와 실패의 합으로 나눈 비율입니다.", "완료 또는 실패 이벤트가 아직 없으면 비율 대신 —로 표시합니다."],
    playback_started_30d: ["첫 재생", "최근 30일 동안 오디오북 읽기 화면을 열어 재생을 시작한 횟수입니다.", "고유 사용자 수가 아니라 시작 횟수이므로 같은 사용자가 여러 번 포함될 수 있습니다."],
    total_audiobooks: ["보관함 오디오북", "사용자 보관함에 저장된 오디오북의 총 개수입니다.", "보조 수치는 최근 30일 생성 실패 이벤트 수입니다."],
};

function renderPeople(people) {
    const list = document.getElementById("metricPageList");
    list.replaceChildren();
    if (!people.length) {
        const item = document.createElement("li");
        item.className = "metric-page-empty";
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
        meta.className = "metric-page-meta";
        identity.append(name, email);
        item.append(identity, meta);
        list.append(item);
    });
}

async function loadMetricPage() {
    const metricName = window.location.pathname.split("/").pop();
    const detail = metricDetails[metricName];
    const status = document.getElementById("metricPageStatus");
    const content = document.getElementById("metricPageContent");
    const token = localStorage.getItem("authToken");
    if (!detail || !token) {
        status.textContent = "관리자만 접근할 수 있습니다.";
        return;
    }
    try {
        const response = await fetch("/api/admin/metrics", {
            headers: { "Authorization": `Bearer ${token}` },
            cache: "no-store",
        });
        if (response.status === 401 || response.status === 403) {
            status.textContent = "관리자만 접근할 수 있습니다.";
            return;
        }
        if (!response.ok) throw new Error("지표를 불러오지 못했습니다.");
        const metrics = await response.json();
        document.getElementById("metricPageTitle").textContent = detail[0];
        document.getElementById("metricPageValue").textContent = formatMetric(metricName, metrics[metricName]);
        document.getElementById("metricPageDescription").textContent = detail[1];
        document.getElementById("metricPageBasis").textContent = detail[2];
        renderPeople(metrics.metric_details?.[metricName] || []);
        content.hidden = false;
        status.textContent = "";
    } catch (error) {
        console.error(error);
        status.textContent = "지표를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.";
    }
}

loadMetricPage();
