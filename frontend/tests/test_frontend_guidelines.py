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
ADMIN_HTML = ROOT_DIR / "frontend" / "admin.html"
APP_HTML = ROOT_DIR / "frontend" / "app.html"


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

def test_admin_html_is_standalone_capable_but_not_translucent_status_bar():
    """admin.html은 standalone을 선언하되 black-translucent는 쓰지 않는다.

    실기기 계측으로 확인한 내용이다. status-bar-style을 black-translucent로
    두면 iOS가 웹뷰를 화면 맨 위(y=0)에 붙이면서도 높이는 상태바를 뺀
    793pt(852-59)로 잡는다. 그러면 화면 아래 59pt가 웹뷰 바깥이 되어,
    bottom:0으로 붙인 시트 아래에 웹뷰가 그릴 수 없는 띠가 남는다
    (innerHeight=793 / screen.height=852 / 카드 실제 렌더 끝 793으로 실측).
    translucent를 빼면 웹뷰가 상태바 아래에서 시작해 화면 바닥과 맞는다.
    """
    admin_html = ADMIN_HTML.read_text(encoding="utf-8")

    assert 'name="apple-mobile-web-app-capable"' in admin_html
    assert 'viewport-fit=cover' in admin_html
    # 주석에도 이 단어가 나오므로 실제 meta 태그만 본다.
    assert not re.search(r'<meta[^>]*apple-mobile-web-app-status-bar-style', admin_html)

def test_reader_highlight_never_overrides_body_text_color():
    """재생 중 문장 강조가 글자색을 바꾸지 않는지 확인한다.

    OS 다크모드용 폴백 블록에 color가 남아 있으면, 위쪽 테마 규칙이
    background-color만 덮어쓰기 때문에 그 color가 테마와 무관하게 살아남는다.
    실제로 OS 다크모드 기기에서 라이트·웜 테마를 쓰면 밝은 금색 배경 위에
    흰 글자(#fff5eb)가 찍혀 대비가 1.1:1까지 떨어졌다(사실상 안 보임).
    """
    css = STYLE_CSS.read_text(encoding="utf-8")
    dark_theme = css.split("@media (prefers-color-scheme: dark)", 1)[1]
    highlight_rule = dark_theme.split(".reader-sentence.highlight {", 1)[1].split("}", 1)[0]

    assert "background-color" in highlight_rule
    assert "color:" not in highlight_rule.replace("background-color:", "")

def test_reader_sentence_padding_closes_gaps_between_wrapped_lines():
    """여러 줄로 감기는 문장의 강조 배경이 한 덩어리로 보이는지 확인한다.

    인라인 요소의 배경은 글자 높이만큼만 칠해져서, 줄 간격이 넓으면 줄마다
    배경이 끊겨 본문이 조각난 것처럼 보였다. 세로 여백을
    "(줄 높이 - 글자 실제 높이) / 2"로 잡아야 위아래 줄 배경이 맞닿는다.
    글꼴마다 실제 높이가 달라 --reader-glyph-height를 Reader_View가 넘겨준다.
    """
    css = STYLE_CSS.read_text(encoding="utf-8")
    sentence_rule = css.split("\n.reader-sentence {", 1)[1].split("}", 1)[0]

    assert "--reader-line-height" in sentence_rule
    assert "--reader-glyph-height" in sentence_rule

    reader_view = (ROOT_DIR / "frontend" / "Reader" / "Reader_View.vue").read_text(encoding="utf-8")
    assert "'--reader-glyph-height'" in reader_view
    # 명조/고딕의 실측값이 다르므로 하나로 고정하면 한쪽에 틈이나 겹침이 남는다.
    assert "1.46em" in reader_view and "1.52em" in reader_view

def test_progress_bar_touch_area_is_larger_than_the_visible_line():
    """진행 바의 실제 터치 영역이 보이는 선(4px)보다 넓은지 확인한다.

    손가락으로 4px를 정확히 누를 수는 없다. 보이는 두께는 그대로 두고
    ::before로 위아래만 넓힌다. 12px보다 더 넓히면 바로 위 본문 문장의
    터치를 뺏는다(실측: -14px 지점이 이미 .reader-sentence).
    """
    css = STYLE_CSS.read_text(encoding="utf-8")

    assert ".player-progress-bar::before" in css
    hit_area = css.split(".player-progress-bar::before {", 1)[1].split("}", 1)[0]
    assert "position: absolute" in hit_area
    assert "inset:" in hit_area

def test_light_reader_theme_is_not_pure_white():
    """라이트 테마 읽기 배경이 순백이 아닌지 확인한다.

    순백(#fff)은 장시간 읽기에 눈이 부시다. 미색으로 낮춰도 본문 대비는
    16:1로 WCAG AAA를 크게 넘는다.
    """
    css = STYLE_CSS.read_text(encoding="utf-8")
    light_theme = css.split('[data-app-theme="light"] .reader-container', 1)[1].split("}", 1)[0]

    assert "--reader-bg:" in light_theme
    background = light_theme.split("--reader-bg:", 1)[1].split(";", 1)[0].strip().lower()
    assert background not in ("#fff", "#ffffff", "white")

def test_reader_highlight_thickens_strokes_without_changing_glyph_width():
    """재생 중 문장을 굵게 보이게 하되 글자 폭은 그대로 두는지 확인한다.

    font-weight를 올리면 글자 폭이 함께 바뀌어 줄바꿈이 밀린다. 재생 중
    문장이 넘어갈 때마다 본문이 들썩이게 된다(실측: weight 700에서 첫 줄
    끝이 330.9px → 328.8px로 밀려 글자 하나가 다음 줄로 넘어갔다).
    text-shadow는 획만 덧그려서 레이아웃이 전혀 바뀌지 않는다.
    """
    css = STYLE_CSS.read_text(encoding="utf-8")
    highlight_rule = css.split("\n.reader-sentence.highlight {", 1)[1].split("}", 1)[0]

    assert "text-shadow" in highlight_rule
    assert "font-weight" not in highlight_rule
    # px로 고정하면 글자 크기를 키웠을 때 두께 비율이 깨진다.
    assert "em" in highlight_rule.split("text-shadow:", 1)[1].split(";", 1)[0]

def test_progress_bar_supports_dragging_with_a_time_tooltip():
    """진행 바를 끌어서 이동할 수 있고, 끄는 동안 시각을 보여주는지 확인한다.

    두 시간짜리 경전에서 탭 한 번으로 원하는 지점을 짚기는 어렵다. 놓기
    전까지는 실제로 옮기지 않아야 손을 뗄 곳을 보고 정할 수 있다.
    """
    reader_view = (ROOT_DIR / "frontend" / "Reader" / "Reader_View.vue").read_text(encoding="utf-8")
    css = STYLE_CSS.read_text(encoding="utf-8")

    assert "@pointerdown=" in reader_view
    assert "@pointermove=" in reader_view
    assert "@pointerup=" in reader_view
    # 드래그가 취소돼도(다른 앱으로 전환 등) 말풍선이 남으면 안 된다.
    assert "@pointercancel=" in reader_view
    assert "player-progress-tooltip" in reader_view
    assert ".player-progress-tooltip" in css

def test_secondary_player_controls_are_not_dimmed_by_opacity():
    """보조 재생 컨트롤(반복·속도·타이머)의 대비가 깎이지 않는지 확인한다.

    이미 muted 색이라 대비가 5.03:1인데 opacity 0.75를 곱하면 3.09:1까지
    떨어져 UI 요소 기준(3:1)에 겨우 걸친다(웜 테마에서 실측). 활성/비활성은
    색과 배경으로 이미 구분되므로 투명도를 겹쳐 쓸 이유가 없다.
    """
    css = STYLE_CSS.read_text(encoding="utf-8")
    rule = css.split(".btn-reader-secondary {", 1)[1].split("}", 1)[0]
    # 주석에도 "opacity"라는 낱말이 나오므로 선언만 본다.
    declarations = re.sub(r"/\*.*?\*/", "", rule, flags=re.S)

    assert "color: var(--text-muted)" in declarations
    assert "opacity" not in declarations

def test_long_reader_title_can_be_expanded_by_tapping():
    """긴 제목을 눌러 전체를 볼 수 있는지 확인한다.

    제목은 한 줄 말줄임이라 화면에서 끝을 알 수 없다. 모바일에는 hover
    툴팁이 없어 title 속성만으로는 부족하므로, 눌러서 펼치게 한다.
    """
    reader_view = (ROOT_DIR / "frontend" / "Reader" / "Reader_View.vue").read_text(encoding="utf-8")
    css = STYLE_CSS.read_text(encoding="utf-8")

    assert "isTitleExpanded" in reader_view
    assert "is-expanded" in reader_view
    expanded = css.split(".reader-book-title.is-expanded {", 1)[1].split("}", 1)[0]
    assert "white-space: normal" in expanded

def test_layout_vars_and_stuck_transitions_resync_when_page_becomes_visible():
    """화면이 다시 보일 때 바 높이를 재측정하고 멈춘 전환을 끝내는지 확인한다.

    브라우저는 숨겨진 화면의 렌더링 단계를 건너뛴다. 그래서 ResizeObserver
    콜백이 전달되지 않아 --tab-bar-h 같은 변수가 낡은 값으로 굳고, 시작만
    하고 진행되지 않은 CSS 전환이 그대로 멈춘다 — 백그라운드에 있다가
    PWA로 돌아오면 미니 플레이어가 반쯤 올라온 채로 굳어 있었다.
    (실측: transform이 translateY(71px)에 멈춘 채 show 클래스는 붙어 있고,
    getAnimations().finish()를 부르면 제자리로 돌아왔다.)
    """
    home_view = (ROOT_DIR / "frontend" / "Home" / "Home_View.vue").read_text(encoding="utf-8")

    assert 'addEventListener("visibilitychange"' in home_view
    assert "getAnimations()" in home_view
    assert "finish()" in home_view
    # 높이 재측정도 같은 자리에서 함께 해야 한다.
    handler = home_view.split("function onVisibilityChangeForLayout", 1)[1].split("\n}", 1)[0]
    assert "measureBarHeights()" in handler

def test_reader_buttons_do_not_duplicate_aria_label_with_title():
    """읽기 화면 버튼에 title 속성이 없는지 확인한다.

    iOS에서 버튼을 길게 누르면 title이 네이티브 툴팁으로 뜬다. 재생 버튼을
    누를 때마다 툴팁이 보인다는 제보가 있었다. aria-label이 이미 이름을
    제공하므로 title은 중복이고, 화면에 방해만 된다.
    """
    for name in ["Reader/Reader_View.vue", "Reader/ReaderControls/ReaderControls_View.vue"]:
        source = (ROOT_DIR / "frontend" / name).read_text(encoding="utf-8")
        assert 'title="' not in source, f"{name}에 title 속성이 남아 있습니다"
        # 이름표까지 사라지면 안 된다 — aria-label은 유지해야 한다.
        assert 'aria-label="' in source
