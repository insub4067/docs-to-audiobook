import re
import subprocess
from pathlib import Path

import pytest


ROOT_DIR = Path(__file__).resolve().parents[1]
APP_JS = ROOT_DIR / "static" / "app.js"
UTILS_JS = ROOT_DIR / "static" / "js" / "utils.js"
AUTH_JS = ROOT_DIR / "static" / "js" / "auth.js"
PWA_JS = ROOT_DIR / "static" / "js" / "pwa.js"
NOTIFICATIONS_JS = ROOT_DIR / "static" / "js" / "notifications.js"
GENERATION_STATUS_JS = ROOT_DIR / "static" / "js" / "generation-status.js"
GENERATION_JS = ROOT_DIR / "static" / "js" / "generation.js"
VOICES_JS = ROOT_DIR / "static" / "js" / "voices.js"
WEB_SPEECH_JS = ROOT_DIR / "static" / "js" / "web-speech.js"
READER_CONTROLS_JS = ROOT_DIR / "static" / "js" / "reader-controls.js"
LIBRARY_JS = ROOT_DIR / "static" / "js" / "library.js"
READER_JS = ROOT_DIR / "static" / "js" / "reader.js"
SW_JS = ROOT_DIR / "static" / "sw.js"
STYLE_CSS = ROOT_DIR / "static" / "style.css"
INDEX_HTML = ROOT_DIR / "static" / "index.html"
# admin 대시보드는 Vue SFC(View/State/Logic 분리)로 포팅되어 소스가
# frontend/에 있다. static/admin.html·admin.js는 빌드 산출물(static/dist/admin)
# 로 대체되어 더 이상 존재하지 않는다.
ADMIN_VIEW_VUE = ROOT_DIR / "frontend" / "AdminDashboard" / "AdminDashboard_View.vue"
ADMIN_LOGIC_VUE = ROOT_DIR / "frontend" / "AdminDashboard" / "AdminDashboard_Logic.vue"
ADMIN_METRIC_HTML = ROOT_DIR / "static" / "admin-metric.html"
ADMIN_METRIC_JS = ROOT_DIR / "static" / "admin-metric.js"
MANIFEST = ROOT_DIR / "static" / "manifest.json"

SPLIT_APP_SCRIPTS = [
    "/static/js/toast.js",
    "/static/js/utils.js",
    "/static/js/db.js",
    "/static/js/auth.js",
    "/static/js/pwa.js",
    "/static/js/generation-status.js",
    "/static/js/generation.js",
    "/static/js/voices.js",
    "/static/js/web-speech.js",
    "/static/js/reader-controls.js",
    "/static/js/reader.js",
    "/static/js/library.js",
]


def test_library_controller_renders_db_books_and_exposes_public_contract():
    assert LIBRARY_JS.is_file()
    script = f"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync({str(LIBRARY_JS)!r}, "utf8");
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
const actionSheetBackdrop = {{ classList: {{ contains: () => true, remove() {{}} }}, style: {{}}, addEventListener() {{}} }};
const actionButton = {{ style: {{}}, addEventListener() {{}} }};
const context = {{
  Array,
  Blob,
  URL: {{ revokeObjectURL() {{}} }},
  document: {{
    body: {{ style: {{}} }},
    addEventListener() {{}},
    createElement,
    getElementById(id) {{
      if (id === "actionSheetBackdrop") return actionSheetBackdrop;
      if (["actionShareBtn", "actionDownloadBtn", "actionEditTitleBtn", "actionDeleteBtn", "actionCancelBtn"].includes(id)) return actionButton;
      return null;
    }},
  }},
  window: {{ location: {{ origin: "https://app.example.com" }}, TextAudio: {{}} }},
  navigator: {{}},
  confirm: () => false,
  escapeHtml: (value) => value,
  getAudiobookDisplayTitle: (title) => title,
  getAllAudiobooksFromDB: async () => [{{ id: "same-book", title: "같은 책", sentences: [] }}],
  getAudiobookFromDB: async () => null,
  isLoggedIn: () => false,
  lucide: {{ createIcons() {{}} }},
  showToast() {{}},
  console,
}};
vm.runInNewContext(source, context);
const controller = context.window.TextAudio.createLibraryController({{
  audioList,
  libraryEmpty: {{ style: {{}} }},
  readerControls: {{ getPlaybackSettings: () => ({{ playbackSpeed: 1, repeatMode: "off" }}) }},
  openReaderMode() {{}},
  getCurrentAudio: () => null,
  rememberModalFocus() {{}},
  restoreModalFocus() {{}},
  objectUrls: {{}},
}});
for (const name of ["initialize", "load", "render", "sync", "savePlaybackState", "closeActionSheetIfOpen"]) {{
  if (typeof controller[name] !== "function") throw new Error(`공개 메서드가 없습니다: ${{name}}`);
}}
(async () => {{
  await controller.render();
  const sharedRows = audioList.children.filter((item) => item.innerHTML.includes('data-id="same-book"'));
  if (sharedRows.length !== 1) throw new Error("DB 오디오북을 한 개의 행으로 렌더링하지 않았습니다.");
  if (controller.closeActionSheetIfOpen() !== true) throw new Error("열린 액션시트를 닫지 않았습니다.");
}})().catch((error) => {{ console.error(error); process.exit(1); }});
"""
    subprocess.run(["node", "-e", script], check=True)


def test_reader_controller_opens_local_audio_and_auto_scrolls_current_sentence():
    assert READER_JS.is_file()
    script = f"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync({str(READER_JS)!r}, "utf8");
function element() {{
  const classes = new Set();
  return {{
    style: {{ setProperty() {{}} }}, textContent: "", innerHTML: "", clientHeight: 400,
    classList: {{ add: (name) => classes.add(name), remove: (name) => classes.delete(name), toggle(name, enabled) {{ enabled ? classes.add(name) : classes.delete(name); }}, contains: (name) => classes.has(name) }},
    addEventListener(name, listener) {{ this[name] = listener; }}, appendChild(child) {{ (this.children ||= []).push(child); }},
    querySelector() {{ return null; }}, scrollTo(options) {{ this.lastScroll = options; }},
  }};
}}
const nodes = {{}};
const document = {{
  body: {{ style: {{}} }}, activeElement: null, contains: () => true, addEventListener() {{}},
  getElementById(id) {{ return nodes[id] || null; }},
  createElement() {{
    const node = element();
    Object.defineProperty(node, "id", {{ set(value) {{ this._id = value; nodes[value] = this; }}, get() {{ return this._id; }} }});
    return node;
  }},
}};
const readerAudio = Object.assign(element(), {{ paused: true, duration: 120, currentTime: 0, playbackRate: 1, load() {{ if (this.onloadedmetadata) this.onloadedmetadata(); }}, play: async function() {{ this.paused = false; if (this.onplay) this.onplay(); }}, pause() {{ this.paused = true; if (this.onpause) this.onpause(); }} }});
const readerContent = element();
const readerOverlay = element();
const readerIndexBtn = element();
nodes.readerIndexBtn = readerIndexBtn;
const context = {{
  window: {{ TextAudio: {{
    createReaderControls: () => ({{ initialize() {{}}, applyPlaybackSettings() {{}}, getPlaybackSettings: () => ({{ playbackSpeed: 1, repeatMode: "off" }}), clearSleepTimer() {{}} }}),
    createWebSpeechController: () => ({{ speak() {{}}, stop() {{}} }}),
  }}, location: {{ pathname: "/" }}, fetch: async () => ({{ ok: true }}), localStorage: {{ getItem: () => null, setItem() {{}} }}, setInterval, clearInterval, addEventListener() {{}} }},
  document, Blob, URL: {{ createObjectURL: () => "blob:reader", revokeObjectURL() {{}} }},
  HTMLElement: function HTMLElement() {{}}, requestAnimationFrame: (callback) => callback(),
  setTimeout: (callback) => {{ callback(); return 1; }}, clearTimeout() {{}}, Date, console,
  formatTime: () => "00:00", getAudiobookDisplayTitle: (title) => title, getReaderScrollTarget: () => 180,
  showToast() {{}}, trackProductEvent() {{}}, updateAudiobookPosition() {{}}, saveAudiobookToDB: async () => {{}},
  fetch: async () => ({{ ok: true, json: async () => ({{}}), blob: async () => new Blob() }}),
}};
vm.runInNewContext(source, context);
const elements = {{
  readerOverlay, readerContainer: element(), readerBookTitle: element(), readerShareBtn: element(), closeReaderBtn: element(),
  readerContent, readerAudio, readerPlayPauseBtn: element(), playIconSvg: element(), pauseIconSvg: element(),
  readerCurrentTime: element(), readerDuration: element(), readerProgressBar: Object.assign(element(), {{ getBoundingClientRect: () => ({{ left: 0, width: 100 }}) }}), readerProgressFill: element(),
  readerSkipBackBtn: element(), readerSkipForwardBtn: element(), readerRepeatBtn: element(), readerRepeatText: element(), readerSpeedBtn: element(), readerSpeedText: element(), readerTimerBtn: element(), readerTimerText: element(),
  importLinkBtn: element(), indexSheetList: element(), indexSheetBackdrop: element(), indexSheetCancelBtn: element(), saveSharedBtn: null,
}};
const reader = context.window.TextAudio.createReaderController({{ elements, state: {{}}, services: {{ library: {{ savePlaybackState: async () => {{}}, render() {{}} }} }}, setupSwipeToDismiss() {{}}, rememberModalFocus() {{}}, restoreModalFocus() {{}} }});
for (const name of ["initialize", "open", "getCurrentAudio", "getPlaybackSettings", "closeIndexSheetIfOpen"]) {{ if (typeof reader[name] !== "function") throw new Error(`공개 메서드가 없습니다: ${{name}}`); }}
reader.initialize();
reader.open({{ id: "book-1", title: "책", audioData: new Uint8Array([1]), sentences: [{{ text: "첫 문장", start: 0, end: 1000 }}] }});
readerAudio.currentTime = 0.5;
readerAudio.ontimeupdate();
if (!readerOverlay.classList.contains("show") || reader.getCurrentAudio().id !== "book-1") throw new Error("로컬 오디오북을 리더로 열지 않았습니다.");
if (!readerContent.lastScroll || readerContent.lastScroll.top !== 180) throw new Error("현재 문장을 자동 스크롤하지 않았습니다.");
"""
    subprocess.run(["node", "-e", script], check=True)


def test_reader_replaces_the_shared_save_button_on_each_shared_open():
    script = f"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync({str(READER_JS)!r}, "utf8");
function element() {{
  const classes = new Set();
  return {{
    style: {{ setProperty() {{}} }}, textContent: "", innerHTML: "", clientHeight: 400,
    classList: {{ add: (name) => classes.add(name), remove: (name) => classes.delete(name), toggle(name, enabled) {{ enabled ? classes.add(name) : classes.delete(name); }}, contains: (name) => classes.has(name) }},
    addEventListener(name, listener) {{ this[name] = listener; }}, appendChild() {{}}, querySelector() {{ return null; }}, scrollTo() {{}},
  }};
}}
const nodes = {{}};
const document = {{
  body: {{ style: {{}} }}, addEventListener() {{}}, getElementById: (id) => nodes[id] || null,
  createElement: () => element(), contains: () => true,
}};
const readerAudio = Object.assign(element(), {{ paused: true, duration: 60, currentTime: 0, load() {{ if (this.onloadedmetadata) this.onloadedmetadata(); }}, play: async function() {{ this.paused = false; if (this.onplay) this.onplay(); }}, pause() {{ this.paused = true; if (this.onpause) this.onpause(); }} }});
let activeSaveButton;
let replaceCount = 0;
const saveButtonParent = {{
  replaceChild(newButton, oldButton) {{
    if (oldButton !== activeSaveButton) throw new Error("분리된 저장 버튼을 교체하려 했습니다.");
    oldButton.parentNode = null;
    newButton.parentNode = this;
    activeSaveButton = newButton;
    replaceCount += 1;
  }},
}};
function createSaveButton() {{
  const button = element();
  button.parentNode = saveButtonParent;
  button.cloneNode = () => createSaveButton();
  return button;
}}
activeSaveButton = createSaveButton();
const importLinkBtn = element();
const closeReaderBtn = element();
const context = {{
  window: {{ TextAudio: {{
    createReaderControls: () => ({{ initialize() {{}}, applyPlaybackSettings() {{}}, getPlaybackSettings: () => ({{ playbackSpeed: 1, repeatMode: "off" }}), clearSleepTimer() {{}} }}),
    createWebSpeechController: () => ({{ stop() {{}}, speak() {{}} }}),
  }}, location: {{ pathname: "/" }}, localStorage: {{ getItem: () => null, setItem() {{}} }}, setInterval, clearInterval, addEventListener() {{}} }},
  document, Blob, URL: {{ createObjectURL: () => "blob:test", revokeObjectURL() {{}} }}, requestAnimationFrame: (callback) => callback(),
  setTimeout: (callback) => {{ callback(); return 1; }}, clearTimeout() {{}}, Date, console,
  prompt: () => "https://app.example.com/share/first", confirm: () => false,
  fetch: async () => ({{ ok: true, json: async () => ({{ title: "공유 책", sentences: [], audio_url: "https://audio.example.com/book.mp3" }}) }}),
  formatTime: () => "00:00", getAudiobookDisplayTitle: (title) => title, getReaderScrollTarget: () => 0,
  showToast() {{}}, trackProductEvent() {{}}, updateAudiobookPosition() {{}}, saveAudiobookToDB: async () => {{}},
}};
vm.runInNewContext(source, context);
const elements = {{
  readerOverlay: element(), readerContainer: element(), readerBookTitle: element(), readerShareBtn: element(), closeReaderBtn,
  readerContent: element(), readerAudio, readerPlayPauseBtn: element(), playIconSvg: element(), pauseIconSvg: element(),
  readerCurrentTime: element(), readerDuration: element(), readerProgressBar: Object.assign(element(), {{ getBoundingClientRect: () => ({{ left: 0, width: 100 }}) }}), readerProgressFill: element(),
  readerSkipBackBtn: element(), readerSkipForwardBtn: element(), readerRepeatBtn: element(), readerRepeatText: element(), readerSpeedBtn: element(), readerSpeedText: element(), readerTimerBtn: element(), readerTimerText: element(),
  importLinkBtn, indexSheetList: element(), indexSheetBackdrop: element(), indexSheetCancelBtn: element(), saveSharedBtn: activeSaveButton, readerIndexBtn: element(),
}};
const reader = context.window.TextAudio.createReaderController({{ elements, services: {{ library: {{ savePlaybackState: async () => {{}}, render() {{}} }} }}, setupSwipeToDismiss() {{}}, rememberModalFocus() {{}}, restoreModalFocus() {{}} }});
reader.initialize();
(async () => {{
  await importLinkBtn.click();
  closeReaderBtn.click({{ preventDefault() {{}}, stopPropagation() {{}} }});
  if (activeSaveButton.style.display !== "none") throw new Error("첫 공유 리더 종료에서 활성 저장 버튼을 숨기지 않았습니다.");
  await importLinkBtn.click();
  if (replaceCount !== 2) throw new Error("두 번째 공유 리더 진입에서 저장 버튼을 다시 교체하지 않았습니다.");
}})().catch((error) => {{ console.error(error); process.exit(1); }});
"""
    subprocess.run(["node", "-e", script], check=True)


def test_generation_controller_exposes_initialization_and_pending_generation_contract():
    assert GENERATION_JS.is_file()
    source = GENERATION_JS.read_text(encoding="utf-8")

    assert "TextAudio.createGenerationController" in source
    assert "initialize" in source
    assert "runPendingGeneration" in source


def test_background_notification_client_is_loaded():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert NOTIFICATIONS_JS.is_file()
    assert '<script src="/static/js/notifications.js"></script>' in html


def test_background_job_is_remembered_and_checked_on_resume():
    generation = GENERATION_JS.read_text(encoding="utf-8")
    notifications = NOTIFICATIONS_JS.read_text(encoding="utf-8")
    pwa = PWA_JS.read_text(encoding="utf-8")

    assert "rememberBackgroundJob(jobId, filename)" in generation
    assert "setInterval(checkPendingBackgroundJobs, 30000)" in notifications
    assert "window.__checkPendingBackgroundJobs" in pwa


def test_generation_status_controller_keeps_one_row_per_job_and_removes_it():
    assert GENERATION_STATUS_JS.is_file()
    script = f"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync({str(GENERATION_STATUS_JS)!r}, "utf8");
const audioList = {{
  children: [],
  prepend(item) {{ this.children.unshift(item); item.parent = this; }},
  querySelectorAll(selector) {{
    return selector === ".audio-item-generating"
      ? this.children.filter((item) => item.className.includes("audio-item-generating"))
      : [];
  }},
}};
const libraryEmpty = {{ style: {{ display: "flex" }} }};
const context = {{
  Array,
  document: {{
    createElement() {{
      const status = {{ textContent: "" }};
      return {{
        className: "",
        dataset: {{}},
        innerHTML: "",
        querySelector(selector) {{ return selector === ".generating-status" ? status : null; }},
        remove() {{ this.parent.children = this.parent.children.filter((item) => item !== this); }},
      }};
    }},
  }},
  escapeHtml: (value) => value,
  getAudiobookDisplayTitle: (value) => value.replace(/\\.mp3$/i, ""),
  window: {{}},
}};
vm.runInNewContext(source, context);
const controller = context.window.TextAudio.createGenerationStatusController({{ audioList, libraryEmpty }});
const pending = controller.create("대기 중.mp3");
if (!pending.innerHTML.includes("대기 중") || !pending.className.includes("audio-item-generating")) {{
  throw new Error("전경 생성 작업 행을 만들지 않았습니다.");
}}
const first = controller.show("job-1", "첫 번째.mp3");
const duplicate = controller.show("job-1", "중복.mp3");
if (first !== duplicate || audioList.children.length !== 1) {{
  throw new Error("같은 작업의 생성 행이 중복되었습니다.");
}}
if (!first.innerHTML.includes("첫 번째") || libraryEmpty.style.display !== "none") {{
  throw new Error("생성 행의 제목 또는 빈 상태가 올바르지 않습니다.");
}}
controller.remove("job-1");
if (audioList.children.length !== 0 || libraryEmpty.style.display !== "flex") {{
  throw new Error("완료된 생성 행을 제거하지 않았습니다.");
}}
"""
    subprocess.run(["node", "-e", script], check=True)


def test_voice_controller_loads_voices_and_stops_active_preview():
    assert VOICES_JS.is_file()
    script = f"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync({str(VOICES_JS)!r}, "utf8");
let pauseCount = 0;
const notifications = [];
const voiceSelect = {{
  children: [],
  value: "",
  _innerHTML: "",
  addEventListener(name, handler) {{ this[name] = handler; }},
  appendChild(option) {{
    this.children.push(option);
    if (this.children.length === 1) this.value = option.value;
  }},
  set innerHTML(value) {{ this._innerHTML = value; this.children = []; }},
  get innerHTML() {{ return this._innerHTML; }},
  set selectedIndex(index) {{ if (this.children[index]) this.value = this.children[index].value; }},
}};
const voiceDesc = {{ textContent: "", style: {{}} }};
const voicePreviewLabel = {{ textContent: "미리듣기" }};
const voicePreviewBtn = {{
  disabled: false,
  addEventListener(name, handler) {{ this[name] = handler; }},
}};
const context = {{ window: {{}} }};
vm.runInNewContext(source, context);
const controller = context.window.TextAudio.createVoiceController({{
  voiceSelect,
  voiceDesc,
  voicePreviewBtn,
  voicePreviewLabel,
  fetch: async (url) => url === "/api/voices"
    ? {{ ok: true, json: async () => [{{ short_name: "ko-KR-Test", friendly_name: "테스트", locale: "ko-KR", description: "차분함" }}] }}
    : {{ ok: true, blob: async () => ({{}}) }},
  createOption: () => ({{ value: "", textContent: "" }}),
  createAudio: () => ({{
    pause() {{ pauseCount += 1; }},
    play: async () => undefined,
    onended: null,
    onerror: null,
  }}),
  createObjectURL: () => "blob:preview",
  notify: (...args) => notifications.push(args),
  logError() {{}},
}});
controller.initialize();

(async () => {{
  await controller.loadVoices();
  if (voiceSelect.children.length !== 1 || voiceSelect.value !== "ko-KR-Test") {{
    throw new Error("서버 음성 목록을 선택기에 반영하지 않았습니다.");
  }}
  if (voiceDesc.textContent !== "차분함" || controller.getSelectedVoice() !== "ko-KR-Test") {{
    throw new Error("선택 음성 설명 또는 값을 반영하지 않았습니다.");
  }}
  await voicePreviewBtn.click();
  await voicePreviewBtn.click();
  if (pauseCount !== 1 || voicePreviewLabel.textContent !== "미리듣기" || voicePreviewBtn.disabled) {{
    throw new Error("재생 중인 음성 미리듣기를 정리하지 않았습니다.");
  }}
  if (notifications.length !== 0) throw new Error("성공 흐름에서 오류 알림을 표시했습니다.");
}})().catch((error) => {{ console.error(error); process.exit(1); }});
"""
    subprocess.run(["node", "-e", script], check=True)


def test_web_speech_controller_speaks_stops_and_reports_unsupported_browsers():
    assert WEB_SPEECH_JS.is_file()
    script = f"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync({str(WEB_SPEECH_JS)!r}, "utf8");
const context = {{ window: {{}} }};
vm.runInNewContext(source, context);
let cancelCount = 0;
const spoken = [];
const notifications = [];
const controller = context.window.TextAudio.createWebSpeechController({{
  speechSynthesis: {{
    cancel() {{ cancelCount += 1; }},
    speak(utterance) {{ spoken.push(utterance); }},
  }},
  createUtterance: (text) => ({{ text }}),
  notify: (...args) => notifications.push(args),
}});
controller.speak("본문", "ko-KR", 1.25, 0.8);
if (cancelCount !== 1 || spoken.length !== 1 || spoken[0].text !== "본문") {{
  throw new Error("Web Speech 발화를 시작하지 않았습니다.");
}}
if (spoken[0].lang !== "ko-KR" || spoken[0].rate !== 1.25 || spoken[0].pitch !== 0.8) {{
  throw new Error("Web Speech 발화 설정을 적용하지 않았습니다.");
}}
controller.stop();
if (cancelCount !== 2) throw new Error("Web Speech 발화를 정지하지 않았습니다.");

const unsupported = context.window.TextAudio.createWebSpeechController({{
  speechSynthesis: null,
  createUtterance: (text) => ({{ text }}),
  notify: (...args) => notifications.push(args),
}});
unsupported.speak("본문");
if (notifications.length !== 1 || notifications[0][1] !== "error") {{
  throw new Error("Web Speech 미지원 상태를 알리지 않았습니다.");
}}
"""
    subprocess.run(["node", "-e", script], check=True)


def test_reader_controls_restore_apply_and_cycle_playback_settings():
    assert READER_CONTROLS_JS.is_file()
    script = f"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync({str(READER_CONTROLS_JS)!r}, "utf8");
function createButton() {{
  const classes = new Set();
  return {{
    listeners: {{}},
    classList: {{
      add: (name) => classes.add(name),
      remove: (name) => classes.delete(name),
      toggle(name, enabled) {{ enabled ? classes.add(name) : classes.delete(name); }},
      contains: (name) => classes.has(name),
    }},
    addEventListener(name, handler) {{ this.listeners[name] = handler; }},
    click() {{ return this.listeners.click(); }},
  }};
}}
const skipBackBtn = createButton();
const skipForwardBtn = createButton();
const repeatBtn = createButton();
const speedBtn = createButton();
const timerBtn = createButton();
const repeatText = {{ textContent: "" }};
const speedText = {{ textContent: "" }};
const timerText = {{ textContent: "" }};
const audioListeners = {{}};
const readerAudio = {{
  currentTime: 5,
  duration: 100,
  playbackRate: 1,
  paused: false,
  addEventListener(name, handler) {{ audioListeners[name] = handler; }},
  pause() {{ this.paused = true; }},
  play: async () => undefined,
}};
const values = new Map([
  ["textAudio_playbackSpeed", "1.25"],
  ["textAudio_repeatMode", "all"],
]);
const storage = {{
  getItem: (key) => values.get(key) || null,
  setItem: (key, value) => values.set(key, String(value)),
}};
const context = {{ window: {{}} }};
vm.runInNewContext(source, context);
const controls = context.window.TextAudio.createReaderControls({{
  readerAudio,
  skipBackBtn,
  skipForwardBtn,
  repeatBtn,
  repeatText,
  speedBtn,
  speedText,
  timerBtn,
  timerText,
  storage,
  notify() {{}},
  setInterval: () => 1,
  clearInterval() {{}},
}});
controls.initialize();
let settings = controls.getPlaybackSettings();
if (settings.playbackSpeed !== 1.25 || settings.repeatMode !== "all") {{
  throw new Error("저장된 리더 설정을 복원하지 않았습니다.");
}}
skipBackBtn.click();
if (readerAudio.currentTime !== 0) throw new Error("10초 뒤로 이동 경계를 지키지 않았습니다.");
skipForwardBtn.click();
if (readerAudio.currentTime !== 10) throw new Error("10초 앞으로 이동하지 않았습니다.");
controls.applyPlaybackSettings({{ playbackSpeed: 1.5, repeatMode: "one" }});
settings = controls.getPlaybackSettings();
if (settings.playbackSpeed !== 1.5 || settings.repeatMode !== "one" || readerAudio.playbackRate !== 1.5) {{
  throw new Error("오디오북별 재생 설정을 적용하지 않았습니다.");
}}
speedBtn.click();
repeatBtn.click();
settings = controls.getPlaybackSettings();
if (settings.playbackSpeed !== 2 || settings.repeatMode !== "off") {{
  throw new Error("재생 속도 또는 반복 모드를 순환하지 않았습니다.");
}}
controls.clearSleepTimer();
if (timerText.textContent !== "타이머" || timerBtn.classList.contains("active")) {{
  throw new Error("취침 타이머 UI를 초기화하지 않았습니다.");
}}
"""
    subprocess.run(["node", "-e", script], check=True)


def test_pending_background_job_restores_loading_row_with_saved_title():
    script = f"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync({str(NOTIFICATIONS_JS)!r}, "utf8");
const pendingKey = "textAudio_pendingBackgroundJobs:user-1:job:job-1";
const values = new Map([[pendingKey, JSON.stringify({{ title: "복원할 책.mp3" }})]]);
const restored = [];
const context = {{
  JSON, Date, Math, Promise, Uint8Array, atob() {{}}, clearInterval() {{}},
  console: {{ warn() {{}} }},
  document: {{ getElementById() {{ return null; }} }},
  fetch: async () => ({{ ok: true, json: async () => ({{ status: "processing" }}) }}),
  authHeaders: () => ({{}}),
  getCurrentAuthenticatedUserId: () => "user-1",
  isLoggedIn: () => true,
  localStorage: {{
    get length() {{ return values.size; }}, key: (index) => [...values.keys()][index] || null,
    getItem: (key) => values.get(key) || null, setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  }},
  navigator: {{}}, setInterval: () => 1, setTimeout, showToast() {{}},
  window: {{ __showBackgroundJobLoading: (...args) => restored.push(args) }},
}};
vm.runInNewContext(source, context);

(async () => {{
  await context.initializeBackgroundNotifications();
  if (restored.length !== 1 || restored[0][0] !== "job-1" || restored[0][1] !== "복원할 책.mp3") {{
    throw new Error("저장된 백그라운드 작업의 로딩 행을 복원하지 않았습니다.");
  }}
}})().catch((error) => {{ console.error(error); process.exit(1); }});
"""
    subprocess.run(["node", "-e", script], check=True)


def test_completed_background_job_remains_pending_until_cloud_sync_succeeds():
    script = f"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync({str(NOTIFICATIONS_JS)!r}, "utf8");
const pendingKey = "textAudio_pendingBackgroundJobs:user-1:job:job-1";
const values = new Map([[pendingKey, "1"]]);
const toasts = [];
const removed = [];
const context = {{
  JSON,
  Date,
  Math,
  Promise,
  Uint8Array,
  atob() {{}},
  clearInterval() {{}},
  console: {{ warn() {{}} }},
  document: {{ getElementById() {{ return null; }} }},
  fetch: async () => ({{ ok: true, json: async () => ({{ status: "completed" }}) }}),
  authHeaders: () => ({{}}),
  getCurrentAuthenticatedUserId: () => "user-1",
  isLoggedIn: () => true,
  localStorage: {{
    get length() {{ return values.size; }},
    key: (index) => [...values.keys()][index] || null,
    getItem: (key) => values.get(key) || null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  }},
  navigator: {{}},
  setInterval: () => 1,
  setTimeout,
  showToast: (...args) => toasts.push(args),
  window: {{ __removeBackgroundJobLoading: (jobId) => removed.push(jobId) }},
}};
vm.runInNewContext(source, context);

(async () => {{
  context.window.__syncAudiobooksToCloud = async () => ({{ ok: false }});
  await context.checkPendingBackgroundJobs();
  if (values.get(pendingKey) !== "1" || toasts.length !== 0) {{
    throw new Error("동기화 실패 작업을 완료로 처리했습니다.");
  }}
  if (removed.length !== 0) throw new Error("동기화 실패 전에 로딩 행을 제거했습니다.");

  delete context.window.__syncAudiobooksToCloud;
  await context.checkPendingBackgroundJobs();
  if (values.get(pendingKey) !== "1" || toasts.length !== 0) {{
    throw new Error("동기화 함수가 없는 초기화 순서에서 작업을 제거했습니다.");
  }}

  context.window.__syncAudiobooksToCloud = async () => ({{ ok: true }});
  await context.checkPendingBackgroundJobs();
  if (values.has(pendingKey) || toasts.length !== 1 || removed.join(",") !== "job-1") {{
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
let aborted = false;
const values = new Map([["textAudio_pushSubscriptionOwner", "user-a"]]);
const subscription = {{
  endpoint: "https://fcm.googleapis.com/fcm/send/abc",
  unsubscribe: () => new Promise(() => {{}}),
}};
const context = {{
  AbortController: class {{
    constructor() {{ this.signal = {{}}; }}
    abort() {{ aborted = true; }}
  }},
  Promise,
  authHeaders: () => ({{ Authorization: "Bearer token" }}),
  console: {{ warn() {{}} }},
  fetch: () => new Promise(() => {{}}),
  localStorage: {{
    getItem: (key) => values.get(key) || null,
    removeItem: (key) => values.delete(key),
  }},
  navigator: {{ serviceWorker: {{
    getRegistration: async () => ({{
      pushManager: {{ getSubscription: async () => subscription }},
    }}),
  }} }},
  setTimeout(callback, delay) {{
    if (delay >= 2000) {{ callback(); return 1; }}
    return setTimeout(callback, delay);
  }},
  clearTimeout() {{}},
}};
vm.runInNewContext(source, context);

Promise.race([
  context.unsubscribePushNotifications().then(() => "returned"),
  new Promise((resolve) => setTimeout(() => resolve("timed-out"), 50)),
]).then((result) => {{
  if (result !== "returned") throw new Error("구독 해제로 로그아웃이 멈춥니다.");
  if (!aborted) throw new Error("시간 초과 DELETE 요청을 취소하지 않았습니다.");
  if (values.has("textAudio_pushSubscriptionOwner")) throw new Error("시간 초과 뒤 stale 구독 owner를 남겼습니다.");
}}).catch((error) => {{ console.error(error); process.exit(1); }});
"""
    subprocess.run(["node", "-e", script], check=True)


def test_push_button_initial_state_and_toggle_behave_as_real_switch():
    script = f"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync({str(NOTIFICATIONS_JS)!r}, "utf8");

async function scenario(initialPermission, initialSubscription, failingMethod = null, initialOwner = null) {{
  let permission = initialPermission;
  let subscription = initialSubscription;
  let requestCount = 0;
  let subscribeCount = 0;
  let unsubscribeCount = 0;
  const requests = [];
  const toasts = [];
  const serviceWorkerListeners = {{}};
  const button = {{
    hidden: true,
    disabled: false,
    dataset: {{}},
    addEventListener(name, handler) {{ this[name] = handler; }},
    setAttribute() {{}},
  }};
  const label = {{ textContent: "" }};
  const registration = {{ pushManager: {{
    getSubscription: async () => subscription,
    subscribe: async () => {{
      subscribeCount += 1;
      subscription = {{
        endpoint: "https://fcm.googleapis.com/fcm/send/new",
        toJSON: () => ({{ endpoint: "https://fcm.googleapis.com/fcm/send/new", keys: {{ p256dh: "p", auth: "a" }} }}),
        unsubscribe: async () => {{ unsubscribeCount += 1; return true; }},
      }};
      return subscription;
    }},
  }} }};
  const values = new Map();
  if (initialOwner) values.set("textAudio_pushSubscriptionOwner", initialOwner);
  const localStorage = {{
    get length() {{ return values.size; }},
    key(index) {{ return [...values.keys()][index] || null; }},
    getItem(key) {{ return values.get(key) || null; }},
    setItem(key, value) {{ values.set(key, value); }},
    removeItem(key) {{ values.delete(key); }},
  }};
  const context = {{
    AbortController,
    Date,
    JSON,
    Math,
    Promise,
    Uint8Array,
    atob,
    authHeaders: () => ({{ Authorization: "Bearer token" }}),
    clearInterval() {{}},
    clearTimeout,
    console: {{ warn() {{}} }},
    crypto: {{ randomUUID: () => "tab-1" }},
    document: {{ getElementById: (id) => id === "pushNotificationBtn" ? button : id === "pushNotificationLabel" ? label : null }},
    fetch: async (url, options = {{}}) => {{
      requests.push({{ url, method: options.method || "GET" }});
      if (url === "/api/push/config") return {{ ok: true, json: async () => ({{ enabled: true, public_key: "BA" }} ) }};
      return {{ ok: (options.method || "GET") !== failingMethod, json: async () => ({{}}) }};
    }},
    getCurrentAuthenticatedUserId: () => "user-1",
    isLoggedIn: () => true,
    localStorage,
    navigator: {{ serviceWorker: {{
      ready: Promise.resolve(registration),
      addEventListener: (name, handler) => {{ serviceWorkerListeners[name] = handler; }},
      getRegistration: async () => registration,
    }} }},
    Notification: {{
      get permission() {{ return permission; }},
      requestPermission: async () => {{ requestCount += 1; permission = "granted"; return permission; }},
    }},
    setInterval: () => 1,
    setTimeout,
    showToast: (...args) => toasts.push(args),
    window: {{ PushManager: function() {{}} }},
  }};
  context.window.Notification = context.Notification;
  vm.runInNewContext(source, context);
  await context.initializeBackgroundNotifications();
  return {{ button, context, label, requests, serviceWorkerListeners, toasts, values, counts: () => ({{ requestCount, subscribeCount, unsubscribeCount }}) }};
}}

(async () => {{
  const denied = await scenario("denied", null);
  if (denied.label.textContent !== "알림 차단됨" || !denied.button.disabled) throw new Error("차단 상태를 표시하지 않았습니다.");
  await denied.button.click();
  if (denied.counts().requestCount !== 0) throw new Error("차단 상태에서 권한을 다시 요청했습니다.");

  let unsubscribed = 0;
  const existing = {{
    endpoint: "https://fcm.googleapis.com/fcm/send/existing",
    toJSON: () => ({{}}),
    unsubscribe: async () => {{ unsubscribed += 1; return true; }},
  }};
  const enabled = await scenario("granted", existing, null, "user-1");
  if (enabled.label.textContent !== "완료 알림 켜짐") throw new Error("기존 구독을 켜짐으로 표시하지 않았습니다.");
  await enabled.button.click();
  if (enabled.counts().requestCount !== 0 || unsubscribed !== 1) throw new Error("켜진 토글이 구독 해제로 동작하지 않았습니다.");
  if (!enabled.requests.some((request) => request.method === "DELETE") || enabled.toasts.length !== 1 || enabled.label.textContent !== "완료 알림 꺼짐") {{
    throw new Error("구독 해제 상태 또는 토스트가 정확하지 않습니다.");
  }}

  const accountChanged = await scenario("granted", {{
    endpoint: "https://fcm.googleapis.com/fcm/send/previous-user",
    toJSON: () => ({{ endpoint: "https://fcm.googleapis.com/fcm/send/previous-user", keys: {{ p256dh: "p", auth: "a" }} }}),
    unsubscribe: async () => true,
  }}, null, "user-a");
  if (!accountChanged.requests.some((request) => request.method === "POST") || accountChanged.values.get("textAudio_pushSubscriptionOwner") !== "user-1" || accountChanged.label.textContent !== "완료 알림 켜짐") {{
    throw new Error("계정 전환 뒤 기존 browser 구독을 현재 사용자에게 재귀속하지 않았습니다.");
  }}

  const failedReconcile = await scenario("granted", {{
    endpoint: "https://fcm.googleapis.com/fcm/send/unbound",
    toJSON: () => ({{ endpoint: "https://fcm.googleapis.com/fcm/send/unbound", keys: {{ p256dh: "p", auth: "a" }} }}),
    unsubscribe: async () => true,
  }}, "POST", "user-a");
  if (failedReconcile.label.textContent !== "완료 알림 꺼짐" || failedReconcile.values.get("textAudio_pushSubscriptionOwner") !== "user-a") {{
    throw new Error("기존 구독의 서버 재귀속 실패를 켜짐으로 표시했습니다.");
  }}

  const stickySubscription = {{
    endpoint: "https://fcm.googleapis.com/fcm/send/sticky",
    toJSON: () => ({{}}),
    unsubscribe: async () => false,
  }};
  const failedDisable = await scenario("granted", stickySubscription, "DELETE");
  await failedDisable.button.click();
  if (failedDisable.label.textContent !== "완료 알림 켜짐" || failedDisable.toasts.length !== 1 || failedDisable.toasts[0][1] !== "error") {{
    throw new Error("서버와 브라우저 해제가 모두 실패했는데 꺼짐으로 표시했습니다.");
  }}

  const disabled = await scenario("default", null);
  if (disabled.label.textContent !== "완료 알림 꺼짐") throw new Error("미구독 상태를 꺼짐으로 표시하지 않았습니다.");
  const enabledFromGeneration = await disabled.context.window.__requestPushNotificationSubscription();
  if (!enabledFromGeneration) throw new Error("생성 시 알림 구독 결과를 반환하지 않았습니다.");
  if (disabled.counts().requestCount !== 1 || disabled.counts().subscribeCount !== 1) throw new Error("꺼진 토글에서 구독하지 않았습니다.");
  if (!disabled.requests.some((request) => request.method === "POST") || disabled.toasts.length !== 1 || disabled.label.textContent !== "완료 알림 켜짐") {{
    throw new Error("구독 설정 상태 또는 토스트가 정확하지 않습니다.");
  }}
  await disabled.context.window.__requestPushNotificationSubscription();
  if (disabled.counts().requestCount !== 1 || disabled.counts().subscribeCount !== 1) {{
    throw new Error("이미 등록된 알림을 다시 요청했습니다.");
  }}

  const blockedGeneration = await scenario("denied", null);
  if (await blockedGeneration.context.window.__requestPushNotificationSubscription()) {{
    throw new Error("차단된 권한을 생성 시 다시 요청했습니다.");
  }}
  if (blockedGeneration.counts().requestCount !== 0) throw new Error("차단된 권한 요청 창을 다시 열었습니다.");

  const failedSave = await scenario("default", null, "POST");
  const failedResult = await failedSave.context.window.__requestPushNotificationSubscription();
  if (failedResult) throw new Error("서버 등록 실패를 성공으로 반환했습니다.");
  if (failedSave.counts().unsubscribeCount !== 1 || failedSave.label.textContent !== "완료 알림 꺼짐" || failedSave.toasts.length !== 1) {{
    throw new Error("서버 등록 실패 구독을 브라우저에 켜진 채 남겼습니다.");
  }}

  let messageChecks = 0;
  disabled.context.window.__checkPendingBackgroundJobs = async () => {{ messageChecks += 1; }};
  disabled.serviceWorkerListeners.message({{ data: {{ type: "check_pending_background_jobs" }} }});
  await Promise.resolve();
  if (messageChecks !== 1) throw new Error("서비스워커 확인 메시지를 처리하지 않았습니다.");
}})().catch((error) => {{ console.error(error); process.exit(1); }});
"""
    subprocess.run(["node", "-e", script], check=True)


def test_generation_requests_completion_notification_without_blocking_synthesis():
    script = f"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync({str(GENERATION_JS)!r}, "utf8");

let notificationRequests = 0;
let generationRequests = 0;
function element(overrides = {{}}) {{
  return Object.assign({{
    value: "", textContent: "", disabled: false, style: {{}}, dataset: {{}}, files: [],
    classList: {{ add() {{}}, remove() {{}} }}, listeners: {{}},
    addEventListener(name, handler) {{ this.listeners[name] = handler; }},
    trigger(name, event = {{}}) {{ return this.listeners[name]?.(event); }},
    querySelector() {{ return null; }}, scrollIntoView() {{}}, focus() {{}}, blur() {{}},
  }}, overrides);
}}
const elements = {{
  dropzone: element(), fileInput: element(), fileDetails: element(), fileName: element(), fileSize: element(),
  removeFileBtn: element(), speedSlider: element({{ value: "0" }}), speedVal: element(),
  pitchSlider: element({{ value: "0" }}), pitchVal: element(), generateBtn: element(),
  previewPlaceholder: element(), previewText: element(), charCountBadge: element(),
  audioList: element({{ children: [], prepend(item) {{ this.children.unshift(item); }} }}),
  libraryEmpty: element(), urlInput: element({{ value: "https://example.com/article" }}),
  urlFetchBtn: element({{ querySelector() {{ return element({{ textContent: "가져오기" }}); }} }}),
  urlClearBtn: element(), loginPromptConfirmBtn: element(), headerLoginSlot: element(),
}};
const storage = new Map();
const context = {{
  FormData: class {{ constructor() {{ this.values = {{}}; }} append(key, value) {{ this.values[key] = value; }} }},
  authHeaders: () => ({{}}), anonymousSessionHeaders: () => ({{}}), canStartAnonymousTrial: async () => true,
  console, formatBytes: () => "1 KB", isLoggedIn: () => true, navigator: {{ userAgent: "Desktop" }},
  rememberBackgroundJob() {{}}, showToast() {{}}, syncUrlClearButton() {{}}, trackProductEvent() {{}},
  updateGenerateHint() {{}}, parseInt, setTimeout: (callback) => callback(),
  document: {{
    body: {{ dataset: {{ isAdmin: "false" }} }}, activeElement: null,
    getElementById(id) {{ return elements[id] || null; }},
    querySelector(selector) {{ return selector === ".library-section" ? element() : null; }},
    addEventListener() {{}},
  }},
  sessionStorage: {{
    getItem(key) {{ return storage.get(key) || null; }},
    setItem(key, value) {{ storage.set(key, value); }},
    removeItem(key) {{ storage.delete(key); }},
  }},
  fetch: async (url) => {{
    if (url === "/api/extract-url") return {{ ok: true, json: async () => ({{
      text_id: "text-1", text_access_token: "access-token", filename: "문서.pdf", preview: "본문", char_count: 1234,
    }}) }};
    if (url === "/api/synthesize") {{
      generationRequests += 1;
      return {{ ok: true, json: async () => ({{ job_id: "job-1", background_started: true }}) }};
    }}
    throw new Error(`예상하지 못한 요청: ${{url}}`);
  }},
  window: {{
    innerWidth: 1024,
    __requestPushNotificationSubscription: async () => {{
      notificationRequests += 1;
      throw new Error("알림 등록 실패");
    }},
  }},
}};
vm.runInNewContext(source, context);
const progressStatus = element();
const controller = context.window.TextAudio.createGenerationController({{
  voiceController: {{ getSelectedVoice: () => "ko-KR-SunHiNeural" }},
  generationStatus: {{ create: () => element({{
    querySelector(selector) {{ return selector.includes("fill") ? element() : progressStatus; }}, remove() {{}},
  }}) }},
  openGenerationModal() {{}}, closeGenerationModal() {{}}, openLoginPromptSheet() {{}}, closeLoginPromptSheet() {{}},
  renderLibrary() {{}}, syncWithCloud() {{}},
}});
controller.initialize();

(async () => {{
  await elements.urlFetchBtn.trigger("click");
  await elements.generateBtn.trigger("click");
  if (notificationRequests !== 1) throw new Error("생성 시 완료 알림을 요청하지 않았습니다.");
  if (generationRequests !== 1) throw new Error("알림 실패로 오디오북 생성을 중단했습니다.");
}})().catch((error) => {{ console.error(error); process.exit(1); }});
"""
    subprocess.run(["node", "-e", script], check=True)


@pytest.mark.parametrize("pending_operation,expected_label,expected_toast", [
    ("delete", "완료 알림 꺼짐", "success"),
    ("unsubscribe", "완료 알림 켜짐", "error"),
])
def test_push_button_recovers_after_unsubscribe_operation_never_settles(
    pending_operation, expected_label, expected_toast
):
    script = f"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync({str(NOTIFICATIONS_JS)!r}, "utf8");
const pendingOperation = {pending_operation!r};
let aborted = false;
let currentSubscription;
const toasts = [];
const values = new Map([["textAudio_pushSubscriptionOwner", "user-1"]]);
const button = {{
  hidden: true,
  disabled: false,
  dataset: {{}},
  addEventListener(name, handler) {{ this[name] = handler; }},
  setAttribute() {{}},
}};
const label = {{ textContent: "" }};
currentSubscription = {{
  endpoint: "https://fcm.googleapis.com/fcm/send/pending",
  toJSON: () => ({{}}),
  unsubscribe: () => {{
    if (pendingOperation === "unsubscribe") return new Promise(() => {{}});
    currentSubscription = null;
    return Promise.resolve(true);
  }},
}};
const registration = {{ pushManager: {{
  getSubscription: async () => currentSubscription,
}} }};
const context = {{
  AbortController: class {{
    constructor() {{ this.signal = {{}}; }}
    abort() {{ aborted = true; }}
  }},
  Date, JSON, Math, Promise, Uint8Array, atob,
  authHeaders: () => ({{ Authorization: "Bearer token" }}),
  clearInterval() {{}},
  clearTimeout() {{}},
  console: {{ warn() {{}} }},
  crypto: {{ randomUUID: () => "tab-1" }},
  document: {{ getElementById: (id) => id === "pushNotificationBtn" ? button : id === "pushNotificationLabel" ? label : null }},
  fetch: (url, options = {{}}) => {{
    if (url === "/api/push/config") return Promise.resolve({{ ok: true, json: async () => ({{ enabled: true, public_key: "BA" }}) }});
    if (pendingOperation === "delete" && options.method === "DELETE") return new Promise(() => {{}});
    return Promise.resolve({{ ok: true, json: async () => ({{}}) }});
  }},
  getCurrentAuthenticatedUserId: () => "user-1",
  isLoggedIn: () => true,
  localStorage: {{
    get length() {{ return values.size; }},
    key(index) {{ return [...values.keys()][index] || null; }},
    getItem(key) {{ return values.get(key) || null; }},
    setItem(key, value) {{ values.set(key, value); }},
    removeItem(key) {{ values.delete(key); }},
  }},
  navigator: {{ serviceWorker: {{
    ready: Promise.resolve(registration),
    addEventListener() {{}},
  }} }},
  Notification: {{ permission: "granted", requestPermission: async () => "granted" }},
  setInterval: () => 1,
  setTimeout(callback, delay) {{
    if (delay >= 2000) {{ queueMicrotask(callback); return 1; }}
    return setTimeout(callback, delay);
  }},
  showToast: (...args) => toasts.push(args),
  window: {{ PushManager: function() {{}} }},
}};
context.window.Notification = context.Notification;
vm.runInNewContext(source, context);

(async () => {{
  await context.initializeBackgroundNotifications();
  const outcome = await Promise.race([
    button.click().then(() => "returned"),
    new Promise((resolve) => setTimeout(() => resolve("stuck"), 50)),
  ]);
  if (outcome !== "returned") throw new Error("UI 알림 해제가 영구 대기했습니다.");
  if (!aborted) throw new Error("제한시간 뒤 DELETE 요청을 abort하지 않았습니다.");
  if (button.dataset.busy || button.disabled) throw new Error("제한시간 뒤 버튼 busy 상태를 복구하지 않았습니다.");
  if (label.textContent !== {expected_label!r}) throw new Error("실제 브라우저 구독 상태로 라벨을 복구하지 않았습니다.");
  if (toasts.length !== 1 || toasts[0][1] !== {expected_toast!r}) throw new Error("제한시간 결과를 정확한 토스트로 표시하지 않았습니다.");
}})().catch((error) => {{ console.error(error); process.exit(1); }});
"""
    subprocess.run(["node", "-e", script], check=True)


def test_pending_jobs_are_isolated_by_user_and_concurrent_adds_are_not_lost():
    script = f"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync({str(NOTIFICATIONS_JS)!r}, "utf8");
const values = new Map();
let serveStaleArray = true;
let currentUserId = "user-a";
const storage = {{
  get length() {{ return values.size; }},
  key(index) {{ return [...values.keys()][index] || null; }},
  getItem(key) {{
    if (serveStaleArray && key === "textAudio_pendingBackgroundJobs") return "[]";
    return values.get(key) || null;
  }},
  setItem(key, value) {{ values.set(key, value); }},
  removeItem(key) {{ values.delete(key); }},
}};
function makeContext() {{
  const context = {{
    Date, JSON, Math, Promise, Uint8Array, atob,
    clearInterval() {{}},
    console: {{ warn() {{}} }},
    crypto: {{ randomUUID: () => "tab" }},
    document: {{ getElementById: () => null }},
    getCurrentAuthenticatedUserId: () => currentUserId,
    isLoggedIn: () => true,
    localStorage: storage,
    navigator: {{}},
    setInterval: () => 1,
    setTimeout,
    showToast() {{}},
    window: {{}},
  }};
  vm.runInNewContext(source, context);
  return context;
}}
const firstTab = makeContext();
const secondTab = makeContext();
firstTab.rememberBackgroundJob("job-a1");
secondTab.rememberBackgroundJob("job-a2");
serveStaleArray = false;
const userAJobs = firstTab.readPendingBackgroundJobs().sort().join(",");
if (userAJobs !== "job-a1,job-a2") throw new Error(`동시 추가 작업이 유실됐습니다: ${{userAJobs}}`);
currentUserId = "user-b";
if (firstTab.readPendingBackgroundJobs().length !== 0) throw new Error("A 계정 작업이 B 계정에 노출됐습니다.");
firstTab.rememberBackgroundJob("job-b1");
if (firstTab.readPendingBackgroundJobs().join(",") !== "job-b1") throw new Error("B 계정 작업 저장에 실패했습니다.");
currentUserId = "user-a";
if (firstTab.readPendingBackgroundJobs().sort().join(",") !== "job-a1,job-a2") throw new Error("A 계정 namespace를 복원하지 못했습니다.");
"""
    subprocess.run(["node", "-e", script], check=True)


def test_multiple_tabs_claim_completed_job_before_showing_one_toast():
    script = f"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync({str(NOTIFICATIONS_JS)!r}, "utf8");
const values = new Map();
const toasts = [];
let releaseSync;
const syncGate = new Promise((resolve) => {{ releaseSync = resolve; }});
let secondTab;
let secondCheck;
let injectedConcurrentClaim = false;
const storage = {{
  get length() {{ return values.size; }},
  key(index) {{ return [...values.keys()][index] || null; }},
  getItem(key) {{
    if (key.includes(":claim:") && !injectedConcurrentClaim) {{
      injectedConcurrentClaim = true;
      secondCheck = secondTab.checkPendingBackgroundJobs();
      return null;
    }}
    return values.get(key) || null;
  }},
  setItem(key, value) {{ values.set(key, value); }},
  removeItem(key) {{ values.delete(key); }},
}};
let tabNumber = 0;
function makeContext() {{
  const tabId = `tab-${{++tabNumber}}`;
  const context = {{
    Date, JSON, Math, Promise, Uint8Array, atob,
    authHeaders: () => ({{}}),
    clearInterval() {{}},
    console: {{ warn() {{}} }},
    crypto: {{ randomUUID: () => tabId }},
    document: {{ getElementById: () => null }},
    fetch: async () => ({{ ok: true, json: async () => ({{ status: "completed" }}) }}),
    getCurrentAuthenticatedUserId: () => "user-a",
    isLoggedIn: () => true,
    localStorage: storage,
    navigator: {{}},
    setInterval: () => 1,
    setTimeout,
    showToast: (...args) => toasts.push(args),
    window: {{ __syncAudiobooksToCloud: async () => syncGate }},
  }};
  vm.runInNewContext(source, context);
  return context;
}}
const firstTab = makeContext();
secondTab = makeContext();
firstTab.rememberBackgroundJob("job-1");
(async () => {{
  const firstCheck = firstTab.checkPendingBackgroundJobs();
  await Promise.resolve();
  if (!secondCheck) throw new Error("동시 claim 경쟁을 만들지 못했습니다.");
  releaseSync({{ ok: true }});
  await Promise.all([firstCheck, secondCheck]);
  if (toasts.length !== 1) throw new Error(`완료 토스트가 ${{toasts.length}}번 표시됐습니다.`);
  if (firstTab.readPendingBackgroundJobs().length !== 0) throw new Error("완료 작업을 한 번 제거하지 않았습니다.");
}})().catch((error) => {{ console.error(error); process.exit(1); }});
"""
    subprocess.run(["node", "-e", script], check=True)


def test_auth_exposes_only_current_authenticated_user_id_to_local_clients():
    script = f"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync({str(AUTH_JS)!r}, "utf8");
const element = () => ({{
  style: {{}}, dataset: {{}}, hidden: false, textContent: "", src: "",
  setAttribute() {{}}, removeAttribute() {{}}, querySelector() {{ return null; }},
}});
const elements = new Map();
const windowListeners = {{}};
let reloads = 0;
const context = {{
  document: {{
    body: {{ dataset: {{}} }},
    getElementById(id) {{
      if (["headerGoogleBtn", "googleLoginBtn", "authMessage"].includes(id)) return null;
      if (!elements.has(id)) elements.set(id, element());
      return elements.get(id);
    }},
    querySelector() {{ return null; }},
  }},
  location: {{ reload() {{ reloads += 1; }} }},
  localStorage: {{ getItem() {{ return null; }} }},
  setupSocialLogin() {{}},
  window: {{ addEventListener(name, handler) {{ windowListeners[name] = handler; }} }},
}};
vm.runInNewContext(source, context);
context.showAppUI({{ id: "user-a", email: "a@example.com" }}, "token");
if (context.getCurrentAuthenticatedUserId() !== "user-a") throw new Error("로그인 사용자 id bridge가 없습니다.");
context.showAppUI(null, null);
if (context.getCurrentAuthenticatedUserId() !== null) throw new Error("로그아웃 뒤 사용자 id가 남았습니다.");
context.showAppUI({{ id: "user-a", email: "a@example.com" }}, "token-a");
if (typeof windowListeners.storage !== "function") throw new Error("다른 탭 인증 변경을 감지하지 않습니다.");
windowListeners.storage({{ key: "authToken", oldValue: "token-a", newValue: "token-b" }});
if (context.getCurrentAuthenticatedUserId() !== null || reloads !== 1) throw new Error("다른 탭 계정 전환 뒤 stale identity를 유지했습니다.");
"""
    subprocess.run(["node", "-e", script], check=True)


def test_silent_cloud_sync_renders_new_audiobooks_without_a_toast():
    script = f"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync({str(LIBRARY_JS)!r}, "utf8");
const savedEntries = [];
let rendered = 0;
let toasts = 0;
const actionButton = {{ addEventListener() {{}}, style: {{}} }};
const context = {{
  Date,
  Array,
  Map,
  Set,
  Promise,
  window: {{ TextAudio: {{}} }},
  document: {{
    body: {{ style: {{}} }},
    getElementById() {{ return actionButton; }},
    addEventListener() {{}},
    createElement() {{ return {{ addEventListener() {{}}, querySelector() {{ return actionButton; }}, style: {{}}, classList: {{}} }}; }},
  }},
  audioList: {{ children: [], querySelectorAll: () => [], appendChild() {{ rendered += 1; }}, set innerHTML(value) {{}} }},
  fetch: async () => ({{
    ok: true,
    json: async () => ({{ audiobooks: [{{ id: "cloud-book", title: "완료된 책", created_at: "2026-08-01T00:00:00Z" }}] }}),
  }}),
  getAllAudiobooksFromDB: async () => savedEntries,
  authHeaders: () => ({{}}),
  isLoggedIn: () => true,
  saveAudiobookToDB: async (entry) => {{ savedEntries.push(entry); }},
  getAudiobookFromDB: async () => null,
  deleteAudiobookFromDB: async () => {{}},
  escapeHtml: (value) => value,
  getAudiobookDisplayTitle: (value) => value,
  lucide: {{ createIcons() {{}} }},
  showToast: () => {{ toasts += 1; }},
}};
vm.runInNewContext(source, context);
const controller = context.window.TextAudio.createLibraryController({{
  audioList: context.audioList, libraryEmpty: {{ style: {{}} }},
  readerControls: {{ getPlaybackSettings: () => ({{}}) }}, openReaderMode() {{}}, getCurrentAudio: () => null,
  rememberModalFocus() {{}}, restoreModalFocus() {{}}, objectUrls: {{}},
}});

(async () => {{
  const result = await controller.sync({{ silent: true }});
  await new Promise((resolve) => setTimeout(resolve, 0));
  if (result.added !== 1 || rendered !== 1 || toasts !== 0) {{
    throw new Error("silent 동기화가 새 보관함 항목을 렌더링하지 않거나 토스트를 표시합니다.");
  }}
}})().catch((error) => {{ console.error(error); process.exit(1); }});
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


def test_service_worker_precaches_notification_client_with_new_cache_version():
    source = SW_JS.read_text(encoding="utf-8")

    # 정확한 버전 문자열을 박아두면 배포마다(CACHE_NAME을 올릴 때마다) 이
    # 테스트가 매번 깨진다. 버전이 실제로 채워져 있는지만 확인한다.
    assert re.search(r'const CACHE_NAME = "[^"]+";', source)
    assert '"/static/js/reader.js"' in source
    assert '"/static/js/library.js"' in source
    assert '"/static/js/notifications.js"' in source


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
const librarySource = fs.readFileSync({str(LIBRARY_JS)!r}, "utf8");
const generationStatusSource = fs.readFileSync({str(GENERATION_STATUS_JS)!r}, "utf8");
const match = utilsSource.match(/function escapeHtml\\(value\\) \\{{[\\s\\S]*?\\n\\}}/);
if (!match) throw new Error("escapeHtml 함수가 없습니다.");
eval(match[0]);
if (escapeHtml('<img src=x onerror=alert(1)>') !== '&lt;img src=x onerror=alert(1)&gt;') {{
  throw new Error("HTML 특수문자를 이스케이프하지 않습니다.");
}}
if (!generationStatusSource.includes('escapeHtml(getAudiobookDisplayTitle(audioFilename))') || !librarySource.includes('escapeHtml(getAudiobookDisplayTitle(audio.title))')) {{
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
    source = GENERATION_JS.read_text(encoding="utf-8")
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
    source = GENERATION_JS.read_text(encoding="utf-8") + AUTH_JS.read_text(encoding="utf-8")

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
    assert "services.library.load();" in source


def test_library_syncs_playback_and_can_edit_titles():
    source = LIBRARY_JS.read_text(encoding="utf-8")
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert 'fetch(`/api/audiobooks/${entry.cloudId}/playback`' in source
    assert 'method: "PUT"' in source
    assert 'fetch(`/api/audiobooks/${entry.cloudId}`, {' in source
    assert 'method: "PATCH"' in source
    assert 'id="actionEditTitleBtn"' in html


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
    script = """
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync("__LIBRARY_JS__", "utf8");
const pendingReads = [];
const audioList = {
  children: [],
  querySelectorAll: () => [],
  appendChild(item) { this.children.push(item); },
};
Object.defineProperty(audioList, "innerHTML", {
  set(value) {
    if (value !== "") throw new Error("목록 초기화가 빈 문자열이 아닙니다.");
    this.children = [];
  },
});
const actionButton = { addEventListener() {}, style: {} };
const context = {
  Array,
  Promise,
  window: { TextAudio: {} },
  document: {
    body: { style: {} },
    addEventListener() {},
    getElementById() { return actionButton; },
    createElement() {
      const front = { addEventListener() {}, classList: { add() {}, remove() {}, contains() { return false; } }, style: {} };
      const background = { addEventListener() {}, style: {} };
      return { className: "", innerHTML: "", addEventListener() {}, querySelector(selector) {
        if (selector === ".audio-item-front") return front;
        if (selector === ".audio-item-bg") return background;
        if (selector === ".btn-more") return actionButton;
        return null;
      }};
    },
  },
  escapeHtml: (value) => value,
  getAudiobookDisplayTitle: (title) => title,
  getAllAudiobooksFromDB: () => new Promise((resolve) => pendingReads.push(resolve)),
  getAudiobookFromDB: async () => null,
  lucide: { createIcons() {} },
  console,
  showToast() {},
};
vm.runInNewContext(source, context);
const controller = context.window.TextAudio.createLibraryController({
  audioList, libraryEmpty: { style: {} },
  readerControls: { getPlaybackSettings: () => ({}) }, openReaderMode() {}, getCurrentAudio: () => null,
  rememberModalFocus() {}, restoreModalFocus() {}, objectUrls: {},
});

(async () => {
  const firstRender = controller.render();
  const secondRender = controller.render();
  if (pendingReads.length !== 2) throw new Error("겹친 DB 조회가 시작되지 않았습니다.");
  const sharedBook = { id: "same-book", title: "같은 책", sentences: [] };
  pendingReads[1]([sharedBook]);
  await secondRender;
  pendingReads[0]([sharedBook]);
  await firstRender;
  const sharedRows = audioList.children.filter((item) => item.innerHTML.includes('data-id="same-book"'));
  if (sharedRows.length !== 1) throw new Error(`같은 오디오북 행이 ${sharedRows.length}개 남았습니다.`);
})().catch((error) => { console.error(error); process.exit(1); });
""".replace("__LIBRARY_JS__", str(LIBRARY_JS))
    subprocess.run(["node", "-e", script], check=True)
