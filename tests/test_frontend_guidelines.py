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
if (!source.includes('escapeHtml(audioFilename)') || !source.includes('escapeHtml(audio.title)')) {{
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


def test_icon_buttons_and_modal_have_accessible_names_and_roles():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert 'id="logoutBtn" aria-label="로그아웃"' in html
    assert 'id="closeModalBtn" aria-label="닫기"' in html
    assert 'id="generationModal" role="dialog" aria-modal="true"' in html
    assert 'id="actionSheetBackdrop" role="dialog" aria-modal="true"' in html
    assert 'id="actionCancelBtn">닫기</button>' in html
