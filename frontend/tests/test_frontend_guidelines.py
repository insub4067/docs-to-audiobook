import re
import subprocess
from pathlib import Path


# 저장소 루트: frontend/tests/이 파일 기준 두 단계 위.
ROOT_DIR = Path(__file__).resolve().parents[2]
FRONTEND_STATIC = ROOT_DIR / "frontend" / "static"
SW_JS = FRONTEND_STATIC / "sw.js"
STYLE_SHEET_ORDER = [
    "00-tokens.css",
    "01-base.css",
    "02-files.css",
    "03-header-card.css",
    "04-upload-form.css",
    "05-audio-list.css",
    "06-reader.css",
    "07-modal-sheet.css",
    "08-mini-player.css",
    "09-misc.css",
]

STYLE_CSS_DIR = FRONTEND_STATIC / "css"
# style.css는 화면 단위로 나뉘어 있다. 아래 STYLE_SHEET_ORDER가 app.html의
# link 순서이자 곧 캐스케이드 순서이므로, 기존 CSS 테스트들은 그 순서대로
# 이어 붙인 전체를 본다 — 나누기 전과 정확히 같은 것을 검사하게 된다.


def read_all_css() -> str:
    return "\n".join(
        (STYLE_CSS_DIR / name).read_text(encoding="utf-8") for name in STYLE_SHEET_ORDER
    )
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
    css = read_all_css()
    body_rule = css.split("body {", 1)[1].split("}", 1)[0]

    assert "overflow-x: hidden" in body_rule
    assert "overscroll-behavior-y: none" in body_rule
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert "@media (prefers-color-scheme: dark)" in css

def test_pull_refresh_spinner_moves_counterclockwise():
    css = read_all_css()

    assert "nth-child(1)  { animation-delay: -0.916s; }" in css
    assert "nth-child(12) { animation-delay: -0.000s; }" in css

def test_dark_mode_keeps_upload_and_reader_surfaces_dark():
    css = read_all_css()
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
    # 시그니처가 아니라 "목록을 그린다"는 사실만 고정한다. 인자를 하나
    # 늘렸다는 이유로 깨지면 테스트가 리팩토링을 막기만 한다.
    assert 'function renderPeople(' in detail_source
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
    css = read_all_css()
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
    css = read_all_css()
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
    css = read_all_css()

    assert ".player-progress-bar::before" in css
    hit_area = css.split(".player-progress-bar::before {", 1)[1].split("}", 1)[0]
    assert "position: absolute" in hit_area
    assert "inset:" in hit_area

def test_light_reader_theme_is_not_pure_white():
    """라이트 테마 읽기 배경이 순백이 아닌지 확인한다.

    순백(#fff)은 장시간 읽기에 눈이 부시다. 미색으로 낮춰도 본문 대비는
    16:1로 WCAG AAA를 크게 넘는다.
    """
    css = read_all_css()
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
    css = read_all_css()
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
    css = read_all_css()

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
    css = read_all_css()
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
    css = read_all_css()

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

def test_mini_player_progress_bar_is_draggable_with_a_tooltip():
    """미니 플레이어 진행 바도 끌 수 있고 이동 시각을 보여주는지 확인한다.

    미니 플레이어 전체가 "읽기 화면 열기" 버튼이라, 진행 바에서 일어난
    포인터 이벤트가 위로 올라가면 끌기만 해도 리더가 열려 버린다.
    stopPropagation이 빠지면 안 된다.
    """
    view = (ROOT_DIR / "frontend" / "components" / "MiniPlayer" / "MiniPlayer_View.vue").read_text(encoding="utf-8")
    css = read_all_css()

    assert "@pointerdown=" in view and "@pointermove=" in view and "@pointerup=" in view
    assert "@pointercancel=" in view
    assert "player-progress-tooltip" in view
    assert view.count("event.stopPropagation()") >= 3
    assert ".mini-player-progress-bar::before" in css

def test_mini_player_is_placed_without_animation_on_first_entry():
    """앱을 처음 열 때 미니 플레이어가 전환 없이 제자리에 놓이는지 확인한다.

    첫 화면을 그리는 도중 시작된 CSS 전환이 끝까지 진행되지 않고 반쯤
    올라온 채로 굳는 일이 있었다(최초 진입에서만 재현). 이미 듣던 게
    있다는 뜻이라 미끄러져 올라올 이유도 없다.
    """
    home_view = (ROOT_DIR / "frontend" / "Home" / "Home_View.vue").read_text(encoding="utf-8")
    restore = home_view.split("async function restoreLastPlayedSession", 1)[1].split("\n}", 1)[0]

    assert "settleMiniPlayer" in restore

def test_mini_player_claims_the_touch_gesture_for_swiping():
    """미니 플레이어 스와이프가 실제로 동작할 조건을 갖췄는지 확인한다.

    ⚠️ touch-action이 기본값이면 브라우저가 손가락 움직임을 스크롤로 판정해
    가져가 버린다. 우리에게는 pointermove 대신 pointercancel이 오고, 스와이프가
    통째로 죽는다(실제로 그렇게 배포됐다 — 진행 바 드래그만 되고 스와이프는
    안 됐다).

    setPointerCapture도 필요하다. 손가락이 미니 플레이어 밖으로 나가면 그
    뒤의 move/up이 오지 않기 때문이다. 진행 바 드래그는 이걸 부르고 있어
    혼자만 동작했다.
    """
    css = read_all_css()
    view = (ROOT_DIR / "frontend" / "components" / "MiniPlayer" / "MiniPlayer_View.vue").read_text(encoding="utf-8")

    rule = css.split(".mini-player {", 1)[1].split("}", 1)[0]
    assert "touch-action: none" in rule

    down = view.split("function onRootPointerDown", 1)[1].split("\n}", 1)[0]
    assert "setPointerCapture" in down

def test_mini_player_slides_only_the_title_not_the_whole_bar():
    """좌우로 넘길 때 바 전체가 아니라 제목만 미끄러지는지 확인한다.

    유튜브 뮤직 참고 — 바는 제자리에 있고 곡 정보만 지나간다. 진행 바와
    재생 버튼까지 통째로 밀면 조작 중인 컨트롤이 손가락을 따라 도망간다.
    아래로 내릴 때는 반대로 바 전체가 내려가는 게 맞다.
    """
    view = (ROOT_DIR / "frontend" / "components" / "MiniPlayer" / "MiniPlayer_View.vue").read_text(encoding="utf-8")
    css = read_all_css()

    # 루트에는 세로(내리기) 스타일만, 제목에는 가로 스타일만 붙는다.
    assert ':style="dismissStyle"' in view
    assert ':style="titleSlideStyle"' in view
    assert "mini-player-title-slot" in view
    assert ".mini-title-next-enter-from" in css
    assert ".mini-title-prev-enter-from" in css


# style.css는 4,176줄 한 덩어리였다. 컴포넌트는 78개로 잘 쪼개 놓고 스타일만
# 통짜라, 어디를 고쳐야 하는지 찾는 데만 시간이 걸렸다. 화면 단위로 나눴다.
#
# 나누는 순간 새 위험이 생긴다 — CSS는 나중에 온 규칙이 앞을 덮으므로
# **link 순서가 곧 캐스케이드**다. 파일 하나를 빼먹거나 순서를 바꾸면
# 화면이 미묘하게 깨지는데, 이런 건 테스트가 없으면 몇 주 동안 아무도 모른다.


def test_app_html_loads_every_stylesheet_in_cascade_order():
    html = APP_HTML.read_text(encoding="utf-8")
    loaded = re.findall(r'<link rel="stylesheet" href="/static/css/([^"]+)">', html)

    assert loaded == STYLE_SHEET_ORDER


def test_every_stylesheet_file_exists_and_none_is_orphaned():
    """목록에 없는 파일이 css/에 남아 있으면 아무 화면에도 안 실린다 —
    고쳐도 반영되지 않는 유령 파일이 되므로 양방향으로 확인한다."""
    on_disk = sorted(path.name for path in (FRONTEND_STATIC / "css").glob("*.css"))

    assert on_disk == sorted(STYLE_SHEET_ORDER)


def test_service_worker_does_not_precache_bundled_stylesheets():
    """분할한 CSS는 빌드 입력이지 런타임 자산이 아니다.

    Vite가 app.html의 link들을 순서대로 하나의 해시 붙은 CSS로 합쳐 넣고,
    빌드 결과 HTML에는 link가 남지 않는다. 즉 앱은 /static/css/*.css를
    절대 요청하지 않는다. 프리캐시에 넣으면 설치할 때마다 아무도 안 쓰는
    파일 10개(약 100KB)를 받아 두게 된다.

    (분할 직후 실제로 이 실수를 했고, 프로덕션 HTML을 확인하고 나서야
    알았다. 그래서 반대 방향으로 고정해 둔다.)"""
    sw = (FRONTEND_STATIC / "sw.js").read_text(encoding="utf-8")

    for name in STYLE_SHEET_ORDER:
        assert f'"/static/css/{name}"' not in sw, name


def test_no_stylesheet_references_the_old_single_file():
    """분할 전 경로가 남아 있으면 404 요청이 조용히 계속 나간다."""
    for path in (APP_HTML, FRONTEND_STATIC / "sw.js"):
        assert "/static/style.css" not in path.read_text(encoding="utf-8"), path.name


MINI_PLAYER_CSS = FRONTEND_STATIC / "css" / "08-mini-player.css"
TAB_BAR_CSS = FRONTEND_STATIC / "css" / "02-files.css"
HOME_VIEW = ROOT_DIR / "frontend" / "Home" / "Home_View.vue"


def test_mini_player_does_not_position_itself_by_measured_tab_bar_height():
    """미니 플레이어는 탭바 높이를 몰라야 한다.

    예전에는 Home_View가 탭바 높이를 재서 --tab-bar-h에 넣고 미니 플레이어의
    bottom으로 썼다. 그런데 탭바에는 padding-bottom: env(safe-area-inset-bottom)이
    있어(아이폰에서 34px) 그 값이 safe-area 반영 전 높이로 굳으면 미니 플레이어가
    딱 그만큼 아래로 내려앉는다. 탭바가 z-index로 더 위라 잘려 보였고, 그게
    "미니 플레이어가 뜨다 마는" 증상이었다.

    브라우저에서 실측한 값(탭바 94px, --tab-bar-h가 60px로 굳은 상태):
      예전 구조 → 34px 겹침 / 스택 구조 → 0px.

    ResizeObserver가 고쳐 주기를 기대할 수는 없다. 화면이 숨겨져 있는 동안에는
    콜백이 전달되지 않아 낡은 값이 그대로 남는 경로가 실제로 있었다.
    """
    css = MINI_PLAYER_CSS.read_text(encoding="utf-8")
    mini_rule = css.split(".mini-player {", 1)[1].split("}", 1)[0]

    assert "--tab-bar-h" not in mini_rule
    assert "position: fixed" not in mini_rule


def test_bottom_bars_stack_owns_the_position_of_both_bars():
    """미니 플레이어와 탭바가 한 스택에 있어야 서로의 높이를 몰라도 된다."""
    home = HOME_VIEW.read_text(encoding="utf-8")
    stack = re.search(r'<div class="bottom-bars">(.*?)</div>', home, re.S)

    assert stack, "두 바를 감싸는 .bottom-bars가 없다"
    # 순서가 뒤집히면 탭바가 미니 플레이어 위로 올라간다.
    assert stack.group(1).index("<MiniPlayerView") < stack.group(1).index("<TabBarView")

    tab_bar_rule = TAB_BAR_CSS.read_text(encoding="utf-8").split(".tab-bar {", 1)[1].split("}", 1)[0]
    assert "position: fixed" not in tab_bar_rule

    stack_rule = read_all_css().split(".bottom-bars {", 1)[1].split("}", 1)[0]
    assert "position: fixed" in stack_rule
    assert "flex-direction: column" in stack_rule


def test_now_playing_row_background_is_opaque():
    """⚠️ 재생 중 강조 배경은 반투명이면 안 된다.

    내 파일 목록의 행 아래에는 스와이프 삭제용 빨간 레이어(.audio-item-bg,
    #ff3b30)가 깔려 있다. 강조 배경에 투명도가 있으면 그게 그대로 비쳐,
    재생 중인 행만 붉게 물든 것처럼 보인다. hover/active 규칙이 이미 같은
    이유로 불투명한 색을 쓴다.

    처음 작업할 때 rgba(...,0.14)로 넣었다가 이 제약을 뒤늦게 발견했다.
    눈으로 보기 전에는 드러나지 않는 종류라 규칙으로 고정해 둔다.
    """
    css = read_all_css()
    rule = css.split(".audio-item.is-playing .audio-item-front {", 1)[1].split("}", 1)[0]
    background = re.search(r"background-color:\s*([^;]+);", rule)

    assert background, "재생 중 강조 배경이 없다"
    assert "rgba" not in background.group(1)
    assert "transparent" not in background.group(1)


def test_service_worker_install_does_not_depend_on_external_cdns():
    """cache.addAll()은 하나라도 실패하면 전부 실패한다. 외부 CDN이 잠깐
    흔들렸다고 서비스 워커 설치가 무산되면 오프라인 캐시와 웹 푸시가 통째로
    죽는다 — 우리 서버는 멀쩡한데도."""
    source = SW_JS.read_text(encoding="utf-8")

    required_block = source[source.index("const REQUIRED_ASSETS"):source.index("const OPTIONAL_ASSETS")]
    assert "https://" not in required_block, "필수 자원에 외부 출처가 섞여 있다"

    optional_block = source[source.index("const OPTIONAL_ASSETS"):]
    assert "unpkg.com" in optional_block
    assert "fonts.googleapis.com" in optional_block
    # 외부 자원은 개별로 담고 실패를 삼켜야 한다.
    assert "allSettled" in source
