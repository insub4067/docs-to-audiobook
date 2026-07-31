import subprocess
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
APP_JS = ROOT_DIR / "static" / "app.js"
STYLE_CSS = ROOT_DIR / "static" / "style.css"
INDEX_HTML = ROOT_DIR / "static" / "index.html"


def test_user_generated_titles_are_escaped_before_html_rendering():
    script = f"""
const fs = require("fs");
const source = fs.readFileSync({str(APP_JS)!r}, "utf8");
const match = source.match(/function escapeHtml\\(value\\) \\{{[\\s\\S]*?\\n\\}}/);
if (!match) throw new Error("escapeHtml 함수가 없습니다.");
eval(match[0]);
if (escapeHtml('<img src=x onerror=alert(1)>') !== '&lt;img src=x onerror=alert(1)&gt;') {{
  throw new Error("HTML 특수문자를 이스케이프하지 않습니다.");
}}
if (!source.includes('escapeHtml(getAudiobookDisplayTitle(audioFilename))') || !source.includes('escapeHtml(getAudiobookDisplayTitle(audio.title))')) {{
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

    assert 'id="logoutBtn" aria-label="로그아웃"' in html
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
const source = fs.readFileSync({str(APP_JS)!r}, "utf8");
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
const source = fs.readFileSync({str(APP_JS)!r}, "utf8");
const start = source.indexOf("function getAudiobookDisplayTitle(title)");
const end = source.indexOf("\\n}}", start) + 2;
if (start < 0 || end < 2) throw new Error("오디오북 표시 제목 함수가 없습니다.");
eval(source.slice(start, end));
if (getAudiobookDisplayTitle("데미안.mp3") !== "데미안") throw new Error("MP3 확장자를 숨기지 않습니다.");
if (getAudiobookDisplayTitle("제목") !== "제목") throw new Error("확장자 없는 제목을 바꿉니다.");
"""
    subprocess.run(["node", "-e", script], check=True)
