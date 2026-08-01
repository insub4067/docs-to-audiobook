# 백그라운드 오디오북 완료 알림 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 관리자 대용량 작업의 완료를 앱 복귀·주기 확인·Web Push로 알리고, 당겨서 새로고침 때 오디오북 목록이 중복되는 경쟁 상태를 제거한다.

**Architecture:** Supabase의 `background_synthesis_jobs`를 최종 상태 저장소로 유지하고, `push_subscriptions`는 서버 전용 구독 저장소로 추가한다. 클라이언트는 미확인 `job_id`만 로컬에 보관해 상태를 확인하며, Web Push는 완료를 알려 상태 확인을 앞당기는 보조 채널이다. 목록 렌더는 IndexedDB 조회가 끝난 뒤 현재 DOM을 한 번 교체해 동시 렌더가 같은 항목을 누적하지 못하게 한다.

**Tech Stack:** FastAPI, Supabase/PostgREST, pywebpush 2.3.0, vanilla JavaScript, Service Worker, Push API, pytest, Node VM 기반 프런트 회귀 테스트

## Global Constraints

- iOS Web Push는 홈 화면에 설치된 PWA와 사용자 동작에서 시작된 권한 요청만 지원 대상으로 삼는다.
- 푸시 payload와 시스템 알림에 문서 제목·본문·이메일을 넣지 않는다.
- `VAPID_PRIVATE_KEY`와 Supabase `service_role` 키를 브라우저에 노출하지 않는다.
- Push 전달 실패는 완료된 작업을 실패 상태로 되돌리지 않는다.
- Web Push 설정이 없어도 상태 확인·기존 생성·인증·동기화가 계속 동작해야 한다.
- 프런트 변경이 있으므로 `static/sw.js`의 `CACHE_NAME`을 한 단계 올린다.
- 모든 커밋 메시지는 한국어로 작성하고 검증 후 `main`을 직접 푸시한다.

---

## 파일 구조

- Create: `push_notifications.py` — VAPID 설정 확인, 사용자 구독 대상 완료 푸시, 만료 구독 정리
- Create: `routes/notifications.py` — 푸시 설정·구독 등록/해제·사용자 소유 작업 상태 API
- Create: `static/js/notifications.js` — 브라우저 구독 UI, 미확인 job 저장과 상태 확인
- Create: `tests/test_notifications.py` — API 권한, sender 순서·실패 격리·만료 구독 테스트
- Modify: `routes/tts.py` — 완료 DB 갱신 뒤 sender 호출
- Modify: `main.py` — notifications router 등록
- Modify: `requirements.txt` — `pywebpush==2.3.0` 고정
- Modify: `static/app.js` — 중복 없는 원자 렌더, 백그라운드 job 등록, 알림 초기화 호출
- Modify: `static/js/auth.js` — 프로필 메뉴 알림 버튼과 로그아웃 구독 해제 연결
- Modify: `static/js/pwa.js` — 포그라운드 복귀 상태 확인 브리지 호출
- Modify: `static/index.html` — 알림 메뉴 버튼과 notifications script 로드
- Modify: `static/style.css` — 알림 메뉴 버튼 상태 스타일
- Modify: `static/sw.js` — push/notificationclick 처리, 새 JS 선캐시, 캐시 버전 상승
- Modify: `tests/test_frontend_guidelines.py` — 렌더 경쟁 상태와 알림/PWA 회귀 테스트
- Modify: `SUPABASE_SETUP.md` — push_subscriptions 스키마·최소 권한 기록
- Modify: `docs/large-admin-background-jobs.md` — 완료 통지와 복구 흐름 기록

---

### Task 1: 오디오북 목록 중복 렌더 경쟁 상태 제거

**Files:**
- Modify: `static/app.js:1141-1160`
- Test: `tests/test_frontend_guidelines.py`

**Interfaces:**
- Consumes: `getAllAudiobooksFromDB() -> Promise<Array<audiobook>>`, `audioList`, `libraryEmpty`
- Produces: `renderLibrary() -> Promise<void>` — DB 조회 완료 후 기존 목록을 정확히 한 번 교체

- [ ] **Step 1: 실패하는 렌더 순서 회귀 테스트 작성**

`tests/test_frontend_guidelines.py`에 다음 테스트를 추가한다. 이 테스트를 깨뜨리는 production 변경은 `audioList.innerHTML = ""`를 DB await 앞으로 다시 옮기는 것이다.

```python
def test_library_clears_existing_rows_after_async_database_read():
    source = APP_JS.read_text(encoding="utf-8")
    start = source.index("async function renderLibrary()")
    end = source.index("// --- ActionSheet ---", start)
    render_source = source[start:end]

    read_position = render_source.index("await getAllAudiobooksFromDB()")
    clear_position = render_source.index('audioList.innerHTML = ""')
    assert read_position < clear_position
```

- [ ] **Step 2: 테스트가 현재 구현에서 올바른 이유로 실패하는지 확인**

Run: `pytest tests/test_frontend_guidelines.py::test_library_clears_existing_rows_after_async_database_read -v`

Expected: FAIL because `audioList.innerHTML = ""`가 IndexedDB await보다 앞에 있다.

- [ ] **Step 3: DB 조회 뒤 DOM 교체로 최소 수정**

`renderLibrary()` 시작부를 다음 순서로 바꾼다.

```javascript
async function renderLibrary() {
    try {
        const list = await getAllAudiobooksFromDB();
        const generatingItems = Array.from(audioList.querySelectorAll(".audio-item-generating"));
        audioList.innerHTML = "";

        if (list.length === 0 && generatingItems.length === 0) {
            libraryEmpty.style.display = "flex";
            return;
        }
```

기존의 생성 중 항목 재삽입과 일반 항목 렌더는 그대로 둔다. DB 조회 실패 시 기존 목록을 지우지 않는다.

- [ ] **Step 4: 집중 테스트와 프런트 전체 테스트 통과 확인**

Run: `pytest tests/test_frontend_guidelines.py -v`

Expected: 새 테스트 포함 전체 PASS, 사진처럼 같은 목록이 두 벌 누적되는 비동기 간격이 사라짐.

- [ ] **Step 5: 커밋**

```bash
git add static/app.js tests/test_frontend_guidelines.py
git commit -m "수정: 동시 목록 렌더 중복 방지"
```

---

### Task 2: 서버 Web Push 구독과 작업 상태 API

**Files:**
- Create: `push_notifications.py`
- Create: `routes/notifications.py`
- Create: `tests/test_notifications.py`
- Modify: `main.py:30-46`
- Modify: `requirements.txt`

**Interfaces:**
- Produces: `push_is_configured() -> bool`
- Produces: `send_background_job_ready(user_id: str, job_id: str) -> None`
- Produces: `GET /api/push/config -> {enabled: bool, public_key: str}`
- Produces: `POST /api/push/subscriptions` with `{endpoint, keys: {p256dh, auth}}`
- Produces: `DELETE /api/push/subscriptions` with `{endpoint}`
- Produces: `GET /api/background-jobs/{job_id} -> {status, error, audiobook_id, completed_at}`

- [ ] **Step 1: API 인증·소유권 실패 테스트 작성**

`tests/test_notifications.py`에 인증 없음 401과 다른 사용자 작업 404를 먼저 작성한다.

```python
@pytest.mark.asyncio
async def test_push_subscription_requires_login():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app), base_url="http://test"
    ) as client:
        response = await client.post("/api/push/subscriptions", json={
            "endpoint": "https://push.example/subscription",
            "keys": {"p256dh": "public-key", "auth": "auth-key"},
        })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_background_job_status_hides_other_users_job(mock_supabase):
    mock_supabase.table().select().eq().eq().maybe_single().execute.return_value = MagicMock(data=None)
    with patch("state.require_user_id", return_value="user-2"):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app), base_url="http://test"
        ) as client:
            response = await client.get(
                "/api/background-jobs/job-1", headers={"Authorization": "Bearer token"}
            )
    assert response.status_code == 404
```

- [ ] **Step 2: 서버 테스트 RED 확인**

Run: `pytest tests/test_notifications.py -v`

Expected: FAIL/ERROR because router and endpoints do not exist.

- [ ] **Step 3: 의존성과 최소 API 구현**

`requirements.txt`에 다음을 추가한다.

```text
pywebpush==2.3.0
```

`routes/notifications.py`에는 Pydantic 요청 모델을 두고 endpoint 길이 1~4096자,
각 key 길이 1~2048자를 검증한다. `require_user_id()`로 현재 사용자를 구한 뒤 service-role
클라이언트로 다음 쿼리만 수행한다.

```python
supabase.table("push_subscriptions").upsert({
    "user_id": user_id,
    "endpoint": str(payload.endpoint),
    "p256dh": payload.keys.p256dh,
    "auth": payload.keys.auth,
    "updated_at": datetime.now(timezone.utc).isoformat(),
}, on_conflict="endpoint").execute()
```

삭제는 `.delete().eq("user_id", user_id).eq("endpoint", endpoint)`로 제한한다. 작업 상태는
`.select("status,error,audiobook_id,completed_at").eq("id", job_id).eq("user_id", user_id)`로
조회하고 데이터가 없으면 404를 반환한다. `main.py`에 router를 등록한다.

- [ ] **Step 4: sender 실패·만료 구독 테스트 작성**

```python
def test_ready_push_removes_only_expired_subscriptions(mock_supabase):
    mock_supabase.table().select().eq().execute.return_value = MagicMock(data=[
        {"endpoint": "https://push.example/expired", "p256dh": "p", "auth": "a"},
        {"endpoint": "https://push.example/temporary", "p256dh": "p", "auth": "a"},
    ])
    expired = WebPushException("gone", response=MagicMock(status_code=410))
    temporary = WebPushException("temporary", response=MagicMock(status_code=503))

    with patch("push_notifications.webpush", side_effect=[expired, temporary]):
        send_background_job_ready("user-1", "job-1")

    mock_supabase.table().delete().eq.assert_called_once_with("endpoint", "https://push.example/expired")
```

- [ ] **Step 5: sender RED 확인 후 최소 구현**

Run: `pytest tests/test_notifications.py::test_ready_push_removes_only_expired_subscriptions -v`

Expected: FAIL because `push_notifications.py`가 없다.

`push_notifications.py`에서 환경변수 세 개가 있을 때만 전송한다. `webpush()`에는 다음 값만 보낸다.

```python
webpush(
    subscription_info={
        "endpoint": subscription["endpoint"],
        "keys": {"p256dh": subscription["p256dh"], "auth": subscription["auth"]},
    },
    data=json.dumps({"type": "audiobook_ready", "job_id": job_id}),
    vapid_private_key=os.environ["VAPID_PRIVATE_KEY"],
    vapid_claims={"sub": os.environ["VAPID_SUBJECT"]},
    ttl=86400,
    timeout=10,
)
```

`WebPushException.response.status_code`가 404/410인 endpoint만 service-role로 삭제한다. 다른 예외는
구독을 남기고 함수 밖으로 전파하지 않는다. endpoint나 key는 로그에 쓰지 않는다.

- [ ] **Step 6: 서버 알림 테스트 통과 확인**

Run: `pytest tests/test_notifications.py -v`

Expected: 전체 PASS.

- [ ] **Step 7: 커밋**

```bash
git add push_notifications.py routes/notifications.py tests/test_notifications.py main.py requirements.txt
git commit -m "기능: 웹푸시 구독과 작업 상태 API 추가"
```

---

### Task 3: 작업 완료 이후 푸시 발송 연결

**Files:**
- Modify: `routes/tts.py:441-480`
- Modify: `tests/test_background_jobs.py`

**Interfaces:**
- Consumes: `send_background_job_ready(user_id: str, job_id: str) -> None`
- Preserves: 완료 Storage·audiobooks·background_synthesis_jobs 저장 순서

- [ ] **Step 1: DB 완료 갱신 이후 전송 순서를 고정하는 실패 테스트 작성**

기존 성공 테스트에 호출 기록을 추가한다.

```python
@pytest.mark.asyncio
async def test_background_completion_updates_database_before_push(mock_supabase, tmp_path):
    calls = []
    mock_supabase.table().update.side_effect = lambda payload: calls.append(("update", payload)) or MagicMock()

    with patch("routes.tts.process_synthesis_task", new_callable=AsyncMock), \
         patch("routes.tts._store_background_audiobook", return_value="book-1"), \
         patch("routes.tts.send_background_job_ready", side_effect=lambda *_: calls.append(("push", None))):
        state.jobs["job-1"] = {"status": "completed"}
        await tts.process_background_synthesis_task(
            "job-1", "user-1", "제목", "원문", "voice", "+0%", "+0Hz"
        )

    completed_index = next(i for i, call in enumerate(calls) if call[0] == "update" and call[1].get("status") == "completed")
    push_index = calls.index(("push", None))
    assert completed_index < push_index
```

- [ ] **Step 2: 테스트 RED 확인**

Run: `pytest tests/test_background_jobs.py::test_background_completion_updates_database_before_push -v`

Expected: FAIL because sender 연결이 없다.

- [ ] **Step 3: 완료 갱신 다음에 비차단 발송 연결**

`routes/tts.py`에서 `send_background_job_ready`를 import하고 completed update가 성공한 다음 호출한다.

```python
await asyncio.to_thread(send_background_job_ready, user_id, job_id)
return
```

sender가 내부에서 예외를 격리하므로 푸시 실패가 완료 작업을 실패 분기로 보내지 않는다.

- [ ] **Step 4: 백그라운드 작업 테스트 통과 확인**

Run: `pytest tests/test_background_jobs.py tests/test_notifications.py -v`

Expected: 전체 PASS.

- [ ] **Step 5: 커밋**

```bash
git add routes/tts.py tests/test_background_jobs.py
git commit -m "기능: 백그라운드 완료 후 푸시 발송"
```

---

### Task 4: 클라이언트 구독 UI와 완료 상태 복구

**Files:**
- Create: `static/js/notifications.js`
- Modify: `static/index.html:48-64,390-398`
- Modify: `static/style.css:1932-1968`
- Modify: `static/app.js:909-918,1528-1533,2690-2705`
- Modify: `static/js/auth.js:180-255`
- Modify: `static/js/pwa.js:181-186`
- Test: `tests/test_frontend_guidelines.py`

**Interfaces:**
- Produces: `initializeBackgroundNotifications() -> Promise<void>`
- Produces: `rememberBackgroundJob(jobId: string) -> void`
- Produces: `checkPendingBackgroundJobs() -> Promise<void>`
- Produces: `unsubscribePushNotifications() -> Promise<void>`
- Consumes: `authHeaders()`, `isLoggedIn()`, `showToast()`, `window.__syncAudiobooksToCloud`

- [ ] **Step 1: 클라이언트 구조 실패 테스트 작성**

```python
NOTIFICATIONS_JS = ROOT_DIR / "static" / "js" / "notifications.js"


def test_background_notification_client_is_loaded_and_precached():
    html = INDEX_HTML.read_text(encoding="utf-8")
    sw = SW_JS.read_text(encoding="utf-8")
    assert NOTIFICATIONS_JS.is_file()
    assert '<script src="/static/js/notifications.js"></script>' in html
    assert '"/static/js/notifications.js"' in sw


def test_background_job_is_remembered_and_checked_on_resume():
    app = APP_JS.read_text(encoding="utf-8")
    notifications = NOTIFICATIONS_JS.read_text(encoding="utf-8")
    pwa = PWA_JS.read_text(encoding="utf-8")
    assert "rememberBackgroundJob(jobId)" in app
    assert "setInterval(checkPendingBackgroundJobs, 30000)" in notifications
    assert "window.__checkPendingBackgroundJobs" in pwa
```

- [ ] **Step 2: 프런트 테스트 RED 확인**

Run: `pytest tests/test_frontend_guidelines.py -v`

Expected: FAIL because notifications.js와 메뉴 버튼이 없다.

- [ ] **Step 3: 프로필 메뉴 UI와 구독 토글 구현**

`static/index.html`의 관리자 링크 다음에 버튼을 추가한다.

```html
<button class="profile-menu-link" id="pushNotificationBtn" type="button" role="menuitem" hidden>
    <i data-lucide="bell"></i>
    <span id="pushNotificationLabel">완료 알림 받기</span>
</button>
```

`notifications.js`는 `/api/push/config`가 enabled이고 `serviceWorker`, `PushManager`, `Notification`이
모두 있을 때만 버튼을 표시한다. 버튼 클릭에서만 `Notification.requestPermission()`과
`registration.pushManager.subscribe({userVisibleOnly: true, applicationServerKey})`를 호출한다.
구독 JSON을 인증된 POST API에 저장한 뒤 `완료 알림 켜짐`으로 표시한다.

- [ ] **Step 4: 미확인 job 저장과 상태 확인 구현**

localStorage key는 `textAudio_pendingBackgroundJobs` 하나만 사용하고 값은 문자열 job ID 배열이다.

```javascript
async function checkPendingBackgroundJobs() {
    if (!isLoggedIn()) return;
    const pending = readPendingBackgroundJobs();
    for (const jobId of pending) {
        const response = await fetch(`/api/background-jobs/${encodeURIComponent(jobId)}`, {
            headers: authHeaders(),
        });
        if (!response.ok) continue;
        const job = await response.json();
        if (job.status === "completed") {
            await window.__syncAudiobooksToCloud?.();
            forgetBackgroundJob(jobId);
            showToast("오디오북 생성이 완료되었습니다.", "success");
        } else if (job.status === "error") {
            forgetBackgroundJob(jobId);
            showToast(job.error || "오디오북 생성에 실패했습니다.", "error");
        }
    }
}
```

앱 초기화 후 즉시 한 번 호출하고 pending이 있을 때만 30초 interval을 유지한다. app.js의
`background_started` 분기에서 `rememberBackgroundJob(jobId)`를 호출한다. pwa.js의 visible 복귀에서는
`window.__checkPendingBackgroundJobs?.()`를 호출한다.

- [ ] **Step 5: 로그아웃 구독 해제 연결**

`logout()`이 authToken을 지우기 전에 `unsubscribePushNotifications()`를 best effort로 호출한다.
브라우저 `subscription.unsubscribe()`를 먼저 실행하고, 현재 토큰으로 DELETE API를 호출한다.
실패해도 로그아웃은 계속하며 endpoint/key를 로그에 남기지 않는다.

- [ ] **Step 6: 프런트 테스트 통과 확인**

Run: `node --check static/js/notifications.js && node --check static/app.js && pytest tests/test_frontend_guidelines.py -v`

Expected: 전체 PASS.

- [ ] **Step 7: 커밋**

```bash
git add static/js/notifications.js static/index.html static/style.css static/app.js static/js/auth.js static/js/pwa.js tests/test_frontend_guidelines.py
git commit -m "기능: 백그라운드 완료 상태 확인과 알림 설정"
```

---

### Task 5: 서비스워커 시스템 알림과 캐시 갱신

**Files:**
- Modify: `static/sw.js`
- Test: `tests/test_frontend_guidelines.py`

**Interfaces:**
- Consumes push payload: `{type: "audiobook_ready", job_id: string}`
- Produces OS notification and app focus/open on `notificationclick`

- [ ] **Step 1: 서비스워커 push 동작 실패 테스트 작성**

```python
def test_service_worker_handles_ready_push_and_notification_click():
    source = SW_JS.read_text(encoding="utf-8")
    assert 'self.addEventListener("push"' in source
    assert 'showNotification("TextAudio"' in source
    assert "오디오북 생성이 완료되었습니다." in source
    assert 'self.addEventListener("notificationclick"' in source
    assert "clients.matchAll" in source
    assert "clients.openWindow" in source
```

- [ ] **Step 2: 테스트 RED 확인**

Run: `pytest tests/test_frontend_guidelines.py::test_service_worker_handles_ready_push_and_notification_click -v`

Expected: FAIL because push 이벤트가 없다.

- [ ] **Step 3: 일반 완료 알림과 클릭 처리 구현**

```javascript
self.addEventListener("push", (event) => {
  let payload = {};
  try { payload = event.data ? event.data.json() : {}; } catch (_) {}
  if (payload.type !== "audiobook_ready") return;
  event.waitUntil(self.registration.showNotification("TextAudio", {
    body: "오디오북 생성이 완료되었습니다.",
    icon: "/static/textaudio-icon.png",
    badge: "/static/textaudio-icon.png",
    tag: `audiobook-ready-${payload.job_id || "job"}`,
    data: { job_id: payload.job_id || "" },
  }));
});
```

클릭 시 같은 origin의 window client가 있으면 `focus()`, 없으면 `clients.openWindow("/")`를 호출한다.
알림을 닫고 Push payload를 직접 완료 처리하지 않는다.

- [ ] **Step 4: 캐시 버전과 선캐시 확인**

`CACHE_NAME`을 `2026.08.01.29`로 올리고 `/static/js/notifications.js`를 선캐시에 추가한다.

Run: `pytest tests/test_frontend_guidelines.py -v`

Expected: 전체 PASS.

- [ ] **Step 5: 커밋**

```bash
git add static/sw.js tests/test_frontend_guidelines.py
git commit -m "기능: PWA 완료 푸시 알림 처리"
```

---

### Task 6: Supabase 스키마와 운영 VAPID 설정

**Files:**
- Modify: `SUPABASE_SETUP.md`
- Modify: `docs/large-admin-background-jobs.md`

**Interfaces:**
- Produces table: `public.push_subscriptions`
- Produces Fly secrets: `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT`

- [ ] **Step 1: 문서에 재현 가능한 SQL 작성**

```sql
create table public.push_subscriptions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  endpoint text not null unique,
  p256dh text not null,
  auth text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index push_subscriptions_user_id_idx on public.push_subscriptions(user_id);
alter table public.push_subscriptions enable row level security;
revoke all on table public.push_subscriptions from anon, authenticated;
grant select, insert, update, delete on table public.push_subscriptions to service_role;
```

- [ ] **Step 2: Supabase migration 적용과 검증**

MCP `apply_migration`을 `add_push_subscriptions` 이름으로 적용한다. 그 뒤 `execute_sql`로 다음 네 값이
모두 true인지 확인한다.

```sql
select
  has_table_privilege('service_role', 'public.push_subscriptions', 'SELECT'),
  has_table_privilege('service_role', 'public.push_subscriptions', 'INSERT'),
  has_table_privilege('service_role', 'public.push_subscriptions', 'UPDATE'),
  has_table_privilege('service_role', 'public.push_subscriptions', 'DELETE');
```

- [ ] **Step 3: VAPID 키 생성과 Fly Secret 등록**

P-256 키 한 쌍을 한 번 생성한다. private scalar 32바이트와 uncompressed public point 65바이트를
각각 URL-safe base64(no padding)로 인코딩한다. 공개키는 `VAPID_PUBLIC_KEY`, private scalar는
`VAPID_PRIVATE_KEY`, 연락처는 `VAPID_SUBJECT=mailto:insub4067@gmail.com`으로 Fly Secret에 등록한다.
비밀값 자체는 터미널 출력·문서·커밋에 남기지 않는다.

- [ ] **Step 4: Advisor와 설정 API 확인**

Supabase security/performance Advisor를 실행하고 이번 테이블 관련 Critical/WARN이 없는지 확인한다.
배포 후 인증정보 없이 `GET /api/push/config`가 `enabled: true`와 공개키만 반환하는지 확인한다.

- [ ] **Step 5: 문서 커밋**

```bash
git add SUPABASE_SETUP.md docs/large-admin-background-jobs.md
git commit -m "문서: 완료 푸시 운영 설정 추가"
```

---

### Task 7: 전체 회귀 검증·리뷰·배포

**Files:**
- Verify all changed files

**Interfaces:**
- Produces: 검증된 `main`과 운영 배포

- [ ] **Step 1: 전체 정적·자동 테스트 실행**

Run:

```bash
node --check static/js/notifications.js
node --check static/js/auth.js
node --check static/js/pwa.js
node --check static/app.js
node --check static/sw.js
pytest -q
git diff --check
```

Expected: JS 구문 오류 없음, pytest 전체 PASS, diff 오류 없음.

- [ ] **Step 2: 독립 코드 리뷰**

리뷰어에게 설계 문서, 이 계획, 시작 SHA와 HEAD SHA를 제공한다. Critical/Important는 같은 브랜치에서
수정하고 전체 테스트를 다시 실행한다. Minor는 현재 위험과 범위를 평가해 기록한다.

- [ ] **Step 3: main 직접 푸시**

```bash
git push origin main
```

- [ ] **Step 4: 운영 스모크 테스트**

- `/api/push/config`가 공개키만 반환하는지 확인
- 로그인 후 프로필 메뉴에서 알림 구독이 생성되는지 확인
- 앱 포그라운드에서 테스트 작업 완료 시 한 번만 토스트가 뜨는지 확인
- 서비스워커 push 이벤트에서 일반 완료 알림이 뜨는지 확인
- 당겨서 새로고침을 연속 실행해도 오디오북 목록이 중복되지 않는지 확인
- Fly 로그에 endpoint, 암호화 키, 문서 내용, 인증 토큰이 출력되지 않는지 확인

- [ ] **Step 5: 최종 상태 확인**

Run: `git status -sb && git rev-list --left-right --count origin/main...main`

Expected: 작업 트리 clean, `0 0`.
