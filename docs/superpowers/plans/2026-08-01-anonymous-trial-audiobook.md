# 비로그인 1회 오디오북 체험 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 비로그인 사용자가 기기별로 오디오북 한 권을 생성하고, 로그인 뒤 그 생성본을 자동으로 클라우드에 동기화하게 한다.

**Architecture:** 로그인 요청은 기존 Bearer 토큰 소유권을 유지한다. 비로그인 합성·작업 조회·다운로드에는 브라우저가 만든 익명 세션 ID를 전용 헤더로 보내고, 서버 메모리 작업의 소유자 값으로 검증한다. 브라우저는 `localStorage`의 체험 완료 표식과 IndexedDB의 로컬 오디오북을 사용해 두 번째 생성을 막고 기존 동기화 함수를 재사용한다.

**Tech Stack:** FastAPI, Python/pytest/httpx, Vanilla JavaScript, IndexedDB, Service Worker.

## Global Constraints

- 체험은 브라우저·기기 기준 1회이며, 브라우저 저장소 삭제 후 재체험은 허용한다.
- URL 본문 가져오기·공유·클라우드 저장은 로그인 전용으로 유지한다.
- 익명 합성에도 기존 IP 기반 합성 요청 제한을 유지한다.
- 사용자 ID와 익명 세션 ID가 다른 작업에 접근하면 403을 반환한다.
- 프론트엔드 변경 시 `static/sw.js` 캐시 버전을 올린다.
- 커밋 메시지와 사용자 노출 문구는 한국어로 작성한다.

---

### Task 1: 익명 작업 소유권 검증

**Files:**
- Modify: `main.py:171-190,1042-1114`
- Modify: `tests/test_api.py:49-116`
- Modify: `tests/test_jobs.py:1-89`

**Interfaces:**
- Consumes: `Authorization` 헤더와 `X-Anonymous-Session` 헤더.
- Produces: `resolve_job_owner(authorization, anonymous_session) -> str`, `require_job_owner(job_id, authorization, anonymous_session) -> dict`.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.asyncio
async def test_api_synthesize_allows_anonymous_session():
    with patch("main.process_synthesis_task"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/synthesize",
                data={"text_id": "anonymous-text", "text_access_token": "text-token"},
                headers={"X-Anonymous-Session": "anonymous-session-123456"},
            )
    assert response.status_code == 200

@pytest.mark.asyncio
async def test_get_job_status_rejects_other_anonymous_session():
    jobs["anonymous_job"] = {"status": "pending", "user_id": "anonymous-session-123456"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/job/anonymous_job",
            headers={"X-Anonymous-Session": "anonymous-session-654321"},
        )
    assert response.status_code == 403
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `pytest tests/test_api.py::test_api_synthesize_allows_anonymous_session tests/test_jobs.py::test_get_job_status_rejects_other_anonymous_session -v`

Expected: FAIL because `/api/synthesize` still requires a bearer token and job access only resolves Bearer ownership.

- [ ] **Step 3: Write the minimal server implementation**

```python
def resolve_job_owner(authorization: str, anonymous_session: str) -> str:
    if authorization:
        return require_user_id(authorization)
    session_id = (anonymous_session or "").strip()
    if not session_id:
        raise HTTPException(status_code=401, detail="로그인 또는 체험 세션이 필요합니다.")
    return session_id
```

Use this helper in synthesis, status, audio download, and the legacy MP3 download endpoint. Add `anonymous_session: str = Header(None, alias="X-Anonymous-Session")` only to those endpoints. Keep the existing `user_id` job key so existing cleanup and test fixtures remain compatible.

- [ ] **Step 4: Run focused tests to verify they pass**

Run: `pytest tests/test_api.py::test_api_synthesize_allows_anonymous_session tests/test_api.py::test_api_synthesize_requires_auth tests/test_jobs.py -v`

Expected: PASS. The no-header request remains 401, matching-session access works, and a different anonymous session is 403.

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_api.py tests/test_jobs.py
git commit -m "feat: 비로그인 체험 작업을 보호한다"
```

### Task 2: 브라우저 1회 체험과 로그인 유도

**Files:**
- Modify: `static/app.js:1115-1292,1859-1904,3040-3135`
- Modify: `static/index.html:335-346`
- Modify: `tests/test_frontend_guidelines.py`

**Interfaces:**
- Consumes: `getAllAudiobooksFromDB()`, `isLoggedIn()`, `generateAudiobook()`, `openLoginPromptSheet()`.
- Produces: `anonymousSessionHeaders() -> object`, `canStartAnonymousTrial() -> Promise<boolean>`, `anonymousTrialInProgress` session key.

- [ ] **Step 1: Write the failing frontend-source tests**

```python
def test_anonymous_trial_uses_a_private_session_header_and_one_time_marker():
    source = APP_JS.read_text(encoding="utf-8")
    assert '"X-Anonymous-Session"' in source
    assert 'anonymousTrialUsed' in source
    assert 'anonymousTrialInProgress' in source

def test_login_prompt_explains_second_generation_requires_login():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert "추가 생성은 로그인 후 가능해요" in html
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `pytest tests/test_frontend_guidelines.py::test_anonymous_trial_uses_a_private_session_header_and_one_time_marker tests/test_frontend_guidelines.py::test_login_prompt_explains_second_generation_requires_login -v`

Expected: FAIL because the app has no anonymous session or one-time marker and the current sheet says login is always required.

- [ ] **Step 3: Write the minimal client implementation**

```javascript
async function canStartAnonymousTrial() {
    if (isLoggedIn()) return true;
    if (sessionStorage.getItem("anonymousTrialInProgress") === "true") return false;
    if (localStorage.getItem("anonymousTrialUsed") === "true") return false;
    const books = await getAllAudiobooksFromDB();
    return !books.some(book => !book.isDefault);
}
```

Before a non-logged-in generation, call this function. If false, open the existing login sheet; if true, set the in-progress marker, include `anonymousSessionHeaders()` in synthesis, job status, and audio fetches, then remove the in-progress marker in `finally`. Set `anonymousTrialUsed` only after `saveAudiobookToDB(entry)` succeeds. Update the login-sheet copy only; retain `pendingGeneration` so the second requested book continues after Google login.

- [ ] **Step 4: Run focused tests to verify they pass**

Run: `pytest tests/test_frontend_guidelines.py::test_anonymous_trial_uses_a_private_session_header_and_one_time_marker tests/test_frontend_guidelines.py::test_login_prompt_explains_second_generation_requires_login -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add static/app.js static/index.html tests/test_frontend_guidelines.py
git commit -m "feat: 비로그인 1회 오디오북 생성을 허용한다"
```

### Task 3: 로그인 직후 체험본 자동 동기화와 배포 검증

**Files:**
- Modify: `static/app.js:3099-3135`
- Modify: `static/sw.js:1`
- Modify: `tests/test_frontend_guidelines.py`

**Interfaces:**
- Consumes: `showAppUI(user, token)`, `syncWithCloud()`, IndexedDB 초기화 완료 상태 `db`.
- Produces: 로그인된 앱 UI에서 실행되는 비차단 동기화 호출.

- [ ] **Step 1: Write the failing frontend-source test**

```python
def test_login_syncs_local_audiobooks_after_database_is_ready():
    source = APP_JS.read_text(encoding="utf-8")
    assert "if (loggedIn && db) syncWithCloud();" in source
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `pytest tests/test_frontend_guidelines.py::test_login_syncs_local_audiobooks_after_database_is_ready -v`

Expected: FAIL because `showAppUI` only updates the header and does not trigger an immediate sync.

- [ ] **Step 3: Write the minimal client implementation**

```javascript
if (loggedIn && db) syncWithCloud();
```

Place this after the logged-in profile UI update. Preserve the existing `initDB().then(() => { if (isLoggedIn()) syncWithCloud(); })` fallback for cases where authentication finishes before IndexedDB opens. Increase `CACHE_NAME` in `static/sw.js` by one patch version.

- [ ] **Step 4: Run focused and full verification**

Run: `pytest tests/test_frontend_guidelines.py -v && pytest -q && git diff --check`

Expected: all tests PASS and no whitespace errors.

- [ ] **Step 5: Commit, push, and deploy**

```bash
git add static/app.js static/sw.js tests/test_frontend_guidelines.py
git commit -m "feat: 로그인 후 체험 오디오북을 동기화한다"
git push origin codex/header-profile-menu
flyctl deploy --app docs-to-audiobook
```
