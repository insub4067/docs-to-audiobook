import subprocess
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
APP_JS = ROOT_DIR / "static" / "app.js"
UTILS_JS = ROOT_DIR / "static" / "js" / "utils.js"
AUTH_JS = ROOT_DIR / "static" / "js" / "auth.js"
PWA_JS = ROOT_DIR / "static" / "js" / "pwa.js"
NOTIFICATIONS_JS = ROOT_DIR / "static" / "js" / "notifications.js"
SW_JS = ROOT_DIR / "static" / "sw.js"
STYLE_CSS = ROOT_DIR / "static" / "style.css"
INDEX_HTML = ROOT_DIR / "static" / "index.html"
ADMIN_HTML = ROOT_DIR / "static" / "admin.html"
ADMIN_JS = ROOT_DIR / "static" / "admin.js"
ADMIN_METRIC_HTML = ROOT_DIR / "static" / "admin-metric.html"
ADMIN_METRIC_JS = ROOT_DIR / "static" / "admin-metric.js"
MANIFEST = ROOT_DIR / "static" / "manifest.json"

SPLIT_APP_SCRIPTS = [
    "/static/js/toast.js",
    "/static/js/utils.js",
    "/static/js/db.js",
    "/static/js/auth.js",
    "/static/js/pwa.js",
]


def test_background_notification_client_is_loaded():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert NOTIFICATIONS_JS.is_file()
    assert '<script src="/static/js/notifications.js"></script>' in html


def test_background_job_is_remembered_and_checked_on_resume():
    app = APP_JS.read_text(encoding="utf-8")
    notifications = NOTIFICATIONS_JS.read_text(encoding="utf-8")
    pwa = PWA_JS.read_text(encoding="utf-8")

    assert "rememberBackgroundJob(jobId)" in app
    assert "setInterval(checkPendingBackgroundJobs, 30000)" in notifications
    assert "window.__checkPendingBackgroundJobs" in pwa


def test_completed_background_job_remains_pending_until_cloud_sync_succeeds():
    script = f"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync({str(NOTIFICATIONS_JS)!r}, "utf8");
const values = new Map([["textAudio_pendingBackgroundJobs", JSON.stringify(["job-1"])]]);
const toasts = [];
const context = {{
  JSON,
  Uint8Array,
  atob() {{}},
  clearInterval() {{}},
  console: {{ warn() {{}} }},
  document: {{ getElementById() {{ return null; }} }},
  fetch: async () => ({{ ok: true, json: async () => ({{ status: "completed" }}) }}),
  authHeaders: () => ({{}}),
  isLoggedIn: () => true,
  localStorage: {{ getItem: (key) => values.get(key) || null, setItem: (key, value) => values.set(key, value) }},
  navigator: {{}},
  setInterval: () => 1,
  showToast: (...args) => toasts.push(args),
  window: {{}},
}};
vm.runInNewContext(source, context);

(async () => {{
  context.window.__syncAudiobooksToCloud = async () => ({{ ok: false }});
  await context.checkPendingBackgroundJobs();
  if (values.get("textAudio_pendingBackgroundJobs") !== JSON.stringify(["job-1"]) || toasts.length !== 0) {{
    throw new Error("동기화 실패 작업을 완료로 처리했습니다.");
  }}

  delete context.window.__syncAudiobooksToCloud;
  await context.checkPendingBackgroundJobs();
  if (values.get("textAudio_pendingBackgroundJobs") !== JSON.stringify(["job-1"]) || toasts.length !== 0) {{
    throw new Error("동기화 함수가 없는 초기화 순서에서 작업을 제거했습니다.");
  }}

  context.window.__syncAudiobooksToCloud = async () => ({{ ok: true }});
  await context.checkPendingBackgroundJobs();
  if (values.get("textAudio_pendingBackgroundJobs") !== JSON.stringify([]) || toasts.length !== 1) {{
    throw new Error("동기화 성공 뒤 완료 처리가 한 번 실행되지 않았습니다.");
  }}
}})().catch((error) => {{ console.error(error); process.exit(1); }});
"""
    subprocess.run(["node", "-e", script], check=True)


def test_unsubscribe_does_not_wait_for_service_worker_ready():
    script = f"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync({str(NOTIFICATIONS_JS)!r}, "utf8");
const context = {{
  console: {{ warn() {{}} }},
  navigator: {{ serviceWorker: {{
    ready: new Promise(() => {{}}),
    getRegistration: async () => undefined,
  }} }},
}};
vm.runInNewContext(source, context);

Promise.race([
  context.unsubscribePushNotifications().then(() => "returned"),
  new Promise((resolve) => setTimeout(() => resolve("timed-out"), 50)),
]).then((result) => {{
  if (result !== "returned") throw new Error("서비스워커 준비 대기로 로그아웃이 멈춥니다.");
}}).catch((error) => {{ console.error(error); process.exit(1); }});
"""
    subprocess.run(["node", "-e", script], check=True)


def test_split_app_scripts_exist_and_load_before_app_in_dependency_order():
    html = INDEX_HTML.read_text(encoding="utf-8")
    script_paths = [*SPLIT_APP_SCRIPTS, "/static/app.js"]

    for script_path in SPLIT_APP_SCRIPTS:
        assert (ROOT_DIR / script_path.removeprefix("/")).is_file()

    positions = [html.index(f'<script src="{script_path}"></script>') for script_path in script_paths]
    assert positions == sorted(positions)


def test_service_worker_precaches_split_app_scripts():
    source = SW_JS.read_text(encoding="utf-8")

    for script_path in SPLIT_APP_SCRIPTS:
        assert f'"{script_path}"' in source


def test_pull_refresh_is_safe_before_app_bridges_are_ready():
    script = f"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync({str(PWA_JS)!r}, "utf8");
const listeners = {{}};
const errors = [];
const classList = {{ add() {{}}, remove() {{}}, toggle() {{}}, contains() {{ return false; }} }};
const style = {{ setProperty() {{}}, removeProperty() {{}} }};
const pullElement = {{
  classList,
  style,
  querySelectorAll() {{ return []; }},
}};
const document = {{
  documentElement: {{ classList, style }},
  visibilityState: "visible",
  getElementById(id) {{ return id === "pullRefresh" ? pullElement : {{ classList }}; }},
  querySelector() {{ return null; }},
  addEventListener() {{}},
}};
const window = {{
  innerWidth: 1024,
  scrollY: 0,
  navigator: {{ standalone: false }},
  location: {{ reload() {{}} }},
  matchMedia() {{ return {{ matches: false }}; }},
  addEventListener(name, callback) {{ listeners[name] = callback; }},
}};
const context = {{
  console: {{ error(error) {{ errors.push(error); }}, warn() {{}} }},
  document,
  fetch: async () => ({{ ok: true, json: async () => ({{ build_id: "build" }}), text: async () => "" }}),
  isLoggedIn: () => true,
  navigator: {{ userAgent: "test", serviceWorker: {{}} }},
  setTimeout(callback) {{ callback(); }},
  window,
}};
vm.runInNewContext(source, context);
listeners.touchstart({{ touches: [{{ clientY: 0 }}] }});
listeners.touchmove({{ touches: [{{ clientY: 200 }}], cancelable: true, preventDefault() {{}} }});
listeners.touchend();
if (errors.length > 0) throw errors[0];
"""
    subprocess.run(["node", "-e", script], check=True)


def test_user_generated_titles_are_escaped_before_html_rendering():
    script = f"""
const fs = require("fs");
const utilsSource = fs.readFileSync({str(UTILS_JS)!r}, "utf8");
const appSource = fs.readFileSync({str(APP_JS)!r}, "utf8");
const match = utilsSource.match(/function escapeHtml\\(value\\) \\{{[\\s\\S]*?\\n\\}}/);
if (!match) throw new Error("escapeHtml 함수가 없습니다.");
eval(match[0]);
if (escapeHtml('<img src=x onerror=alert(1)>') !== '&lt;img src=x onerror=alert(1)&gt;') {{
  throw new Error("HTML 특수문자를 이스케이프하지 않습니다.");
}}
if (!appSource.includes('escapeHtml(getAudiobookDisplayTitle(audioFilename))') || !appSource.includes('escapeHtml(getAudiobookDisplayTitle(audio.title))')) {{
  throw new Error("사용자 제목을 안전하게 렌더링하지 않습니다.");
}}
"""
    subprocess.run(["node", "-e", script], check=True)


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


def test_icon_buttons_and_modal_have_accessible_names_and_roles():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert 'id="logoutBtn"' in html
    assert 'aria-label="로그아웃"' in html
    assert 'id="profileMenuBtn"' in html
    assert 'aria-haspopup="menu"' in html
    assert 'id="profileMenu" role="menu" hidden' in html
    assert 'id="closeModalBtn" aria-label="닫기"' in html
    assert 'id="generationModal" role="dialog" aria-modal="true"' in html
    assert 'id="actionSheetBackdrop" role="dialog" aria-modal="true"' in html
    assert 'id="actionCancelBtn">닫기</button>' in html


def test_modals_support_escape_and_restore_focus():
    source = APP_JS.read_text(encoding="utf-8")

    assert "function rememberModalFocus" in source
    assert "function restoreModalFocus" in source
    assert 'document.addEventListener("keydown"' in source
    assert 'event.key !== "Escape"' in source


def test_url_fetch_button_shows_a_spinner_while_loading():
    source = APP_JS.read_text(encoding="utf-8")
    css = STYLE_CSS.read_text(encoding="utf-8")

    assert 'urlFetchBtn.classList.add("is-loading")' in source
    assert 'urlFetchBtn.classList.remove("is-loading")' in source
    assert ".btn-url-fetch.is-loading svg" in css


def test_url_clear_button_is_visible_only_when_input_has_a_value():
    script = f"""
const fs = require("fs");
const source = fs.readFileSync({str(UTILS_JS)!r}, "utf8");
const start = source.indexOf("function syncUrlClearButton(input, button)");
const end = source.indexOf("\\n}}", start) + 2;
if (start < 0 || end < 2) throw new Error("syncUrlClearButton 함수가 없습니다.");
eval(source.slice(start, end));
const button = {{ hidden: true }};
syncUrlClearButton({{ value: "https://example.com" }}, button);
if (button.hidden) throw new Error("입력값이 있는데 초기화 버튼이 숨겨졌습니다.");
syncUrlClearButton({{ value: "" }}, button);
if (!button.hidden) throw new Error("빈 입력값인데 초기화 버튼이 보입니다.");
"""
    subprocess.run(["node", "-e", script], check=True)


def test_audiobook_display_title_hides_file_extension():
    script = f"""
const fs = require("fs");
const source = fs.readFileSync({str(UTILS_JS)!r}, "utf8");
const start = source.indexOf("function getAudiobookDisplayTitle(title)");
const end = source.indexOf("\\n}}", start) + 2;
if (start < 0 || end < 2) throw new Error("오디오북 표시 제목 함수가 없습니다.");
eval(source.slice(start, end));
if (getAudiobookDisplayTitle("데미안.mp3") !== "데미안") throw new Error("MP3 확장자를 숨기지 않습니다.");
if (getAudiobookDisplayTitle("제목") !== "제목") throw new Error("확장자 없는 제목을 바꿉니다.");
"""
    subprocess.run(["node", "-e", script], check=True)


def test_anonymous_trial_uses_a_private_session_header_and_one_time_marker():
    source = APP_JS.read_text(encoding="utf-8") + AUTH_JS.read_text(encoding="utf-8")

    assert '"X-Anonymous-Session"' in source
    assert "anonymousTrialUsed" in source
    assert "anonymousTrialInProgress" in source


def test_login_prompt_explains_second_generation_requires_login():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert "추가 생성은 로그인 후 가능해요" in html


def test_login_does_not_access_database_before_it_initializes():
    source = APP_JS.read_text(encoding="utf-8")

    assert source.index("await initializeAuth();") < source.index("initDB()")
    assert "if (loggedIn && db) syncWithCloud();" not in source
    assert "if (isLoggedIn()) syncWithCloud();" in source


def test_library_syncs_playback_and_can_edit_titles():
    source = APP_JS.read_text(encoding="utf-8")
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert 'fetch(`/api/audiobooks/${entry.cloudId}/playback`' in source
    assert 'method: "PUT"' in source
    assert 'fetch(`/api/audiobooks/${entry.cloudId}`, {' in source
    assert 'method: "PATCH"' in source
    assert 'id="actionEditTitleBtn"' in html


def test_admin_dashboard_renders_retention_metrics():
    html = ADMIN_HTML.read_text(encoding="utf-8")
    source = ADMIN_JS.read_text(encoding="utf-8")

    assert 'data-metric="weekly_active_users"' in html
    assert 'data-metric="week_one_retention_rate"' in html
    assert 'fetch("/api/admin/metrics"' in source
    assert '관리자만 접근할 수 있습니다.' in source


def test_admin_metric_cards_link_to_dedicated_detail_pages():
    html = ADMIN_HTML.read_text(encoding="utf-8")
    detail_html = ADMIN_METRIC_HTML.read_text(encoding="utf-8")
    detail_source = ADMIN_METRIC_JS.read_text(encoding="utf-8")

    assert 'href="/admin/metrics/weekly_active_users"' in html
    assert 'id="metricPageList"' in detail_html
    assert 'function renderPeople(people)' in detail_source
    assert 'fetch("/api/admin/metrics"' in detail_source


def test_profile_menu_can_be_closed_outside_or_with_escape():
    source = AUTH_JS.read_text(encoding="utf-8")

    assert 'if (!userInfo.contains(event.target)) closeProfileMenu();' in source
    assert 'if (event.key === "Escape") closeProfileMenu();' in source


def test_profile_badge_uses_a_short_name_instead_of_google_avatar():
    source = AUTH_JS.read_text(encoding="utf-8")

    assert 'profileName.trim().split(/\\s+/)[0].slice(0, 2)' in source
    assert 'profileImage.hidden = true;' in source


def test_admin_users_have_menu_and_triple_tap_entry_points():
    html = INDEX_HTML.read_text(encoding="utf-8")
    source = AUTH_JS.read_text(encoding="utf-8")

    assert 'id="adminDashboardLink" href="/admin" role="menuitem" hidden' in html
    assert 'id="brandWordmark"' in html
    assert 'adminDashboardLink.hidden = !isAdmin;' in source
    assert 'if (logoTapCount === 3) window.location.assign("/admin");' in source


def test_pwa_uses_the_textaudio_name_and_icon():
    manifest = MANIFEST.read_text(encoding="utf-8")
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert '"name": "TextAudio"' in manifest
    assert '"src": "/static/textaudio-icon.png"' in manifest
    assert 'apple-mobile-web-app-title" content="TextAudio"' in html


def test_reader_scroll_target_uses_viewport_coordinates_for_nested_table_cells():
    script = f"""
const fs = require("fs");
const source = fs.readFileSync({str(UTILS_JS)!r}, "utf8");
const start = source.indexOf("function getReaderScrollTarget(container, activeElement)");
const end = source.indexOf("\\n}}", start) + 2;
if (start < 0 || end < 2) throw new Error("스크롤 위치 계산 함수가 없습니다.");
eval(source.slice(start, end));
const container = {{
  scrollTop: 480,
  clientHeight: 600,
  getBoundingClientRect: () => ({{ top: 100 }}),
}};
const nestedCell = {{
  clientHeight: 60,
  getBoundingClientRect: () => ({{ top: 520 }}),
}};
if (getReaderScrollTarget(container, nestedCell) !== 630) {{
  throw new Error("중첩된 표 셀의 스크롤 위치를 컨테이너 기준으로 계산하지 않습니다.");
}}
"""
    subprocess.run(["node", "-e", script], check=True)


def test_library_clears_existing_rows_after_async_database_read():
    script = f"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync({str(APP_JS)!r}, "utf8");
const start = source.indexOf("async function renderLibrary()");
const end = source.indexOf("// ============================================================", start);
const pendingReads = [];
const audioList = {{
  children: [],
  querySelectorAll(selector) {{
    return selector === ".audio-item-generating"
      ? this.children.filter((item) => item.className.includes("audio-item-generating"))
      : [];
  }},
  appendChild(item) {{ this.children.push(item); }},
}};
Object.defineProperty(audioList, "innerHTML", {{
  set(value) {{
    if (value !== "") throw new Error("목록 초기화가 빈 문자열이 아닙니다.");
    this.children = [];
  }},
}});
function createElement() {{
  const front = {{ addEventListener() {{}}, classList: {{ add() {{}}, remove() {{}}, contains() {{ return false; }} }}, style: {{}} }};
  const background = {{ addEventListener() {{}}, style: {{}} }};
  const moreButton = {{ addEventListener() {{}} }};
  return {{
    className: "",
    innerHTML: "",
    addEventListener() {{}},
    querySelector(selector) {{
      if (selector === ".audio-item-front") return front;
      if (selector === ".audio-item-bg") return background;
      if (selector === ".btn-more") return moreButton;
      return null;
    }},
  }};
}}
const context = {{
  Array,
  audioList,
  libraryEmpty: {{ style: {{}} }},
  document: {{ addEventListener() {{}}, createElement }},
  escapeHtml: (value) => value,
  getAudiobookDisplayTitle: (title) => title,
  getAllAudiobooksFromDB: () => new Promise((resolve) => pendingReads.push(resolve)),
  lucide: {{ createIcons() {{}} }},
  console,
  showToast() {{}},
}};
vm.runInNewContext(`${{source.slice(start, end)}}; this.renderLibrary = renderLibrary;`, context);

(async () => {{
  const firstRender = context.renderLibrary();
  const secondRender = context.renderLibrary();
  if (pendingReads.length !== 2) throw new Error("겹친 DB 조회가 시작되지 않았습니다.");

  const sharedBook = {{ id: "same-book", title: "같은 책", sentences: [] }};
  pendingReads[1]([sharedBook]);
  await secondRender;
  pendingReads[0]([sharedBook]);
  await firstRender;

  const sharedRows = audioList.children.filter((item) => item.innerHTML.includes('data-id="same-book"'));
  if (sharedRows.length !== 1) throw new Error(`같은 오디오북 행이 ${{sharedRows.length}}개 남았습니다.`);
}})().catch((error) => {{ console.error(error); process.exit(1); }});
"""
    subprocess.run(["node", "-e", script], check=True)
