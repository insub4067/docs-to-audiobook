import re
import subprocess
from pathlib import Path


# 저장소 루트: frontend/tests/이 파일 기준 두 단계 위.
ROOT_DIR = Path(__file__).resolve().parents[2]
FRONTEND_STATIC = ROOT_DIR / "frontend" / "static"
SW_JS = FRONTEND_STATIC / "sw.js"
STYLE_CSS = FRONTEND_STATIC / "style.css"
# admin 대시보드는 Vue SFC(View/State/Logic 분리)로 포팅되어 소스가
# frontend/에 있다. static/admin.html·admin.js는 빌드 산출물(static/dist/admin)
# 로 대체되어 더 이상 존재하지 않는다.
ADMIN_VIEW_VUE = ROOT_DIR / "frontend" / "Admin" / "Admin_View.vue"
ADMIN_LOGIC_VUE = ROOT_DIR / "frontend" / "Admin" / "Admin_Logic.vue"
ADMIN_METRIC_HTML = FRONTEND_STATIC / "admin-metric.html"
ADMIN_METRIC_JS = FRONTEND_STATIC / "admin-metric.js"


def test_service_worker_handles_ready_push_and_notification_click():
    source = SW_JS.read_text(encoding="utf-8")

    assert 'self.addEventListener("push"' in source
    assert 'showNotification("TextAudio"' in source
    assert "오디오북 생성이 완료되었습니다." in source
    assert 'self.addEventListener("notificationclick"' in source
    assert "clients.matchAll" in source
    assert "clients.openWindow" in source

def test_service_worker_push_and_click_handlers_use_only_verified_origin_clients():
    script = f"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync({str(SW_JS)!r}, "utf8");
const listeners = {{}};
const notifications = [];
const focused = [];
const opened = [];
let fetchCalls = 0;
let windowClients = [];
const context = {{
  URL,
  caches: {{}},
  clients: {{
    matchAll: async () => windowClients,
    openWindow: async (url) => opened.push(url),
  }},
  fetch: async () => {{ fetchCalls += 1; }},
  self: {{
    location: {{ origin: "https://app.example.com" }},
    registration: {{
      showNotification: async (title, options) => notifications.push({{ title, options }}),
    }},
    addEventListener: (name, handler) => {{ listeners[name] = handler; }},
  }},
}};
vm.runInNewContext(source, context);

async function dispatchPush(payload) {{
  let pending;
  listeners.push({{
    data: {{ json: () => payload }},
    waitUntil: (promise) => {{ pending = promise; }},
  }});
  if (pending) await pending;
}}

async function dispatchClick() {{
  let pending;
  let closed = false;
  listeners.notificationclick({{
    notification: {{ close: () => {{ closed = true; }} }},
    waitUntil: (promise) => {{ pending = promise; }},
  }});
  await pending;
  if (!closed) throw new Error("알림을 닫지 않았습니다.");
}}

(async () => {{
  await dispatchPush({{ type: "other", job_id: "job-1" }});
  if (notifications.length !== 0) throw new Error("audiobook_ready 이외 payload에도 알림을 표시했습니다.");

  await dispatchPush({{ type: "audiobook_ready", job_id: "job-1" }});
  if (notifications.length !== 1 || notifications[0].title !== "TextAudio" || notifications[0].options.body !== "오디오북 생성이 완료되었습니다.") {{
    throw new Error("일반 완료 알림을 표시하지 않았습니다.");
  }}
  if (fetchCalls !== 0) throw new Error("push payload로 상태 API를 직접 호출했습니다.");

  windowClients = [
    {{ url: "not a valid URL", focus: async () => focused.push("invalid") }},
    {{ url: "https://app.example.com.evil/", focus: async () => focused.push("malicious") }},
  ];
  await dispatchClick();
  if (focused.length !== 0 || opened.length !== 1 || opened[0] !== "/") {{
    throw new Error("같은 origin이 아닌 창을 포커스하거나 루트 창을 열지 않았습니다.");
  }}

  const messages = [];
  windowClients = [{{
    url: "https://app.example.com/library",
    focus: async () => focused.push("same-origin"),
    postMessage: (message) => messages.push(message),
  }}];
  await dispatchClick();
  if (focused.length !== 1 || focused[0] !== "same-origin" || opened.length !== 1) {{
    throw new Error("같은 origin 창을 포커스하지 않았습니다.");
  }}
  if (messages.length !== 1 || messages[0].type !== "check_pending_background_jobs") {{
    throw new Error("포커스한 창에 즉시 상태 확인을 요청하지 않았습니다.");
  }}
}})().catch((error) => {{ console.error(error); process.exit(1); }});
"""
    subprocess.run(["node", "-e", script], check=True)

def test_service_worker_has_cache_version_and_no_dead_legacy_assets():
    source = SW_JS.read_text(encoding="utf-8")

    # 정확한 버전 문자열을 박아두면 배포마다(CACHE_NAME을 올릴 때마다) 이
    # 테스트가 매번 깨진다. 버전이 실제로 채워져 있는지만 확인한다.
    assert re.search(r'const CACHE_NAME = "[^"]+";', source)

    # 바닐라 시절의 static/js/*.js와 static/app.js는 Vue SPA로 대체되며
    # 삭제됐다. 프리캐시 목록에 다시 들어오면 install 단계의 cache.addAll이
    # 404로 통째로 실패해 서비스워커가 아예 설치되지 않는다.
    assert "/static/js/" not in source
    assert '"/static/app.js"' not in source

def test_css_supports_motion_and_dark_mode_preferences():
    css = STYLE_CSS.read_text(encoding="utf-8")
    body_rule = css.split("body {", 1)[1].split("}", 1)[0]

    assert "overflow-x: hidden" in body_rule
    assert "overscroll-behavior-y: none" in body_rule
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert "@media (prefers-color-scheme: dark)" in css

def test_pull_refresh_spinner_moves_counterclockwise():
    css = STYLE_CSS.read_text(encoding="utf-8")

    assert "nth-child(1)  { animation-delay: -0.916s; }" in css
    assert "nth-child(12) { animation-delay: -0.000s; }" in css

def test_dark_mode_keeps_upload_and_reader_surfaces_dark():
    css = STYLE_CSS.read_text(encoding="utf-8")
    dark_theme = css.split("@media (prefers-color-scheme: dark)", 1)[1]

    assert ".upload-dropzone" in dark_theme
    assert "background-color: #3a332f" in dark_theme
    assert ".audio-item:active .audio-item-front" in dark_theme
    assert ".reader-container," in dark_theme
    assert ".reader-content" in dark_theme
    assert ".action-sheet" in dark_theme
    assert "background-color: #2f2926" in dark_theme

def test_admin_dashboard_renders_retention_metrics():
    html = ADMIN_VIEW_VUE.read_text(encoding="utf-8")
    source = ADMIN_LOGIC_VUE.read_text(encoding="utf-8")

    assert 'data-metric="weekly_active_users"' in html
    assert 'data-metric="week_one_retention_rate"' in html
    assert 'fetch("/api/admin/metrics"' in source
    assert '관리자만 접근할 수 있습니다.' in source

def test_admin_metric_cards_link_to_dedicated_detail_pages():
    html = ADMIN_VIEW_VUE.read_text(encoding="utf-8")
    detail_html = ADMIN_METRIC_HTML.read_text(encoding="utf-8")
    detail_source = ADMIN_METRIC_JS.read_text(encoding="utf-8")

    assert 'href="/admin/metrics/weekly_active_users"' in html
    assert 'id="metricPageList"' in detail_html
    assert 'function renderPeople(people)' in detail_source
    assert 'fetch("/api/admin/metrics"' in detail_source
