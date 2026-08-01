import subprocess
from pathlib import Path

import pytest


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

    assert "rememberBackgroundJob(jobId, audioFilename)" in app
    assert "setInterval(checkPendingBackgroundJobs, 30000)" in notifications
    assert "window.__checkPendingBackgroundJobs" in pwa


def test_background_loading_row_is_unique_and_removed_by_job_id():
    script = f"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync({str(APP_JS)!r}, "utf8");
const start = source.indexOf("// Background job loading rows");
const end = source.indexOf("// End background job loading rows", start);
if (start < 0 || end < 0) throw new Error("백그라운드 로딩 행 함수가 없습니다.");

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
  audioList,
  libraryEmpty,
  document: {{
    createElement() {{
      const status = {{ textContent: "" }};
      return {{
        className: "",
        dataset: {{}},
        innerHTML: "",
        querySelector(selector) {{ return selector === ".generating-status" ? status : null; }},
        remove() {{
          this.parent.children = this.parent.children.filter((item) => item !== this);
        }},
      }};
    }},
  }},
  escapeHtml: (value) => value,
  getAudiobookDisplayTitle: (value) => value.replace(/\\.mp3$/i, ""),
  window: {{}},
}};
vm.runInNewContext(source.slice(start, end), context);

const first = context.window.__showBackgroundJobLoading("job-1", "첫 번째.mp3");
const duplicate = context.window.__showBackgroundJobLoading("job-1", "중복.mp3");
if (first !== duplicate || audioList.children.length !== 1) {{
  throw new Error("같은 작업의 로딩 행이 중복 생성되었습니다.");
}}
if (!first.innerHTML.includes("첫 번째") || libraryEmpty.style.display !== "none") {{
  throw new Error("로딩 행의 제목 또는 빈 상태가 올바르지 않습니다.");
}}
context.window.__removeBackgroundJobLoading("job-1");
if (audioList.children.length !== 0 || libraryEmpty.style.display !== "flex") {{
  throw new Error("완료된 작업의 로딩 행을 제거하지 않았습니다.");
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
  await disabled.button.click();
  if (disabled.counts().requestCount !== 1 || disabled.counts().subscribeCount !== 1) throw new Error("꺼진 토글에서 구독하지 않았습니다.");
  if (!disabled.requests.some((request) => request.method === "POST") || disabled.toasts.length !== 1 || disabled.label.textContent !== "완료 알림 켜짐") {{
    throw new Error("구독 설정 상태 또는 토스트가 정확하지 않습니다.");
  }}

  const failedSave = await scenario("default", null, "POST");
  await failedSave.button.click();
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
const source = fs.readFileSync({str(APP_JS)!r}, "utf8");
const start = source.indexOf("    let syncing = false;");
const end = source.indexOf("    // 로그아웃(최상위 스코프)", start);
if (start < 0 || end < 0) throw new Error("클라우드 동기화 함수를 찾을 수 없습니다.");
let renders = 0;
let toasts = 0;
const context = {{
  Date,
  Map,
  Set,
  fetch: async () => ({{
    ok: true,
    json: async () => ({{ audiobooks: [{{ id: "cloud-book", title: "완료된 책", created_at: "2026-08-01T00:00:00Z" }}] }}),
  }}),
  fetchPlaybackState: async (entry) => entry,
  getAllAudiobooksFromDB: async () => [],
  authHeaders: () => ({{}}),
  isLoggedIn: () => true,
  renderLibrary: () => {{ renders += 1; }},
  saveAudiobookToDB: async () => {{}},
  showToast: () => {{ toasts += 1; }},
}};
vm.runInNewContext(`${{source.slice(start, end)}}; this.syncWithCloud = syncWithCloud;`, context);

(async () => {{
  const result = await context.syncWithCloud({{ silent: true }});
  if (result.added !== 1 || renders !== 1 || toasts !== 0) {{
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

    assert 'const CACHE_NAME = "2026.08.01.31";' in source
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
