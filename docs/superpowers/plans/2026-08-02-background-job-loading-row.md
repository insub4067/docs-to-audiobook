# 백그라운드 작업 로딩 행 유지 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 서버 백그라운드 오디오북 생성 작업을 보관함의 단일 로딩 행으로 표시하고 새로고침 뒤에도 복원한다.

**Architecture:** 보관함 DOM을 소유한 `static/app.js`가 작업별 로딩 행 생성·제거 함수를 제공하고, `static/js/notifications.js`가 사용자별 `localStorage` 작업 ID와 서버 상태에 맞춰 이 함수를 호출한다. 기존 상태 API와 클라우드 동기화를 재사용하며 서버 스키마는 바꾸지 않는다.

**Tech Stack:** Vanilla JavaScript, FastAPI 상태 API, IndexedDB, pytest에서 실행하는 Node VM 프런트엔드 테스트

## Global Constraints

- 같은 작업 ID의 로딩 행은 한 개만 표시한다.
- 새로고침·앱 재실행 뒤 현재 사용자의 미완료 작업만 복원한다.
- 상태 조회·동기화 실패 시 작업 ID와 로딩 행을 유지한다.
- 완료·실패 시 해당 작업의 로딩 행만 제거한다.
- Push 구독 흐름과 서버 API는 변경하지 않는다.
- 프런트엔드 변경 후 `static/sw.js`의 캐시 버전을 증가시킨다.

---

### Task 1: 작업별 로딩 행 수명주기

**Files:**
- Modify: `static/app.js:850-930`
- Modify: `static/app.js:1142-1165`
- Modify: `static/js/notifications.js:42-115`
- Test: `tests/test_frontend_guidelines.py`

**Interfaces:**
- Consumes: `rememberBackgroundJob(jobId)`, `readPendingBackgroundJobs(userId)`, `/api/background-jobs/{job_id}`
- Produces: `window.__showBackgroundJobLoading(jobId, title?) -> HTMLElement|null`, `window.__removeBackgroundJobLoading(jobId) -> void`

- [ ] **Step 1: 로딩 행 유지·중복 방지·완료 제거를 재현하는 실패 테스트 작성**

```python
def test_background_job_loading_row_is_kept_restored_once_and_removed_on_completion():
    app = APP_JS.read_text(encoding="utf-8")
    notifications = NOTIFICATIONS_JS.read_text(encoding="utf-8")
    branch_start = app.index("if (resData.background_started)")
    branch_end = app.index("// 2. Poll job status", branch_start)
    assert "progressItem.remove();" not in app[branch_start:branch_end]
    assert "window.__showBackgroundJobLoading" in app
    assert "window.__removeBackgroundJobLoading" in app
    assert "window.__showBackgroundJobLoading?.(jobId)" in notifications
    assert "window.__removeBackgroundJobLoading?.(jobId)" in notifications
```

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/test_frontend_guidelines.py -k background_job_loading_row -v`

Expected: FAIL because the background branch removes `progressItem` and loading-row interfaces do not exist.

- [ ] **Step 3: 최소 구현**

`static/app.js`에서 기존 생성 행에 작업 ID를 연결하고 중복 없이 복원할 수 있는 함수를 추가한다.

```javascript
function findBackgroundJobLoading(jobId) {
    return Array.from(audioList.querySelectorAll(".audio-item-generating"))
        .find((item) => item.dataset.backgroundJobId === jobId) || null;
}

function showBackgroundJobLoading(jobId, title = "오디오북") {
    const existing = findBackgroundJobLoading(jobId);
    if (existing) return existing;
    const item = createGeneratingItem(title);
    item.dataset.backgroundJobId = jobId;
    audioList.prepend(item);
    libraryEmpty.style.display = "none";
    return item;
}

function removeBackgroundJobLoading(jobId) {
    findBackgroundJobLoading(jobId)?.remove();
}
```

기존 요청 행은 `background_started` 응답에서 제거하지 않고 `data-background-job-id`를 지정한다. 알림 모듈은 초기 대기 작업 조회 때 `show`를 호출하고, 완료 동기화 성공 또는 오류 상태에서 `remove`를 호출한다.

- [ ] **Step 4: 대상 테스트 통과 확인**

Run: `pytest tests/test_frontend_guidelines.py -k 'background_job_loading_row or background_job_is_remembered or completed_background_job' -v`

Expected: PASS.

- [ ] **Step 5: 구현 커밋**

```bash
git add static/app.js static/js/notifications.js tests/test_frontend_guidelines.py
git commit -m "수정: 백그라운드 생성 상태를 목록에 유지"
```

### Task 2: 캐시 갱신과 회귀 검증

**Files:**
- Modify: `static/sw.js:1`
- Test: `tests/test_frontend_guidelines.py`

**Interfaces:**
- Consumes: `CACHE_NAME`
- Produces: 새 서비스워커 캐시 버전 `2026.08.02.1`

- [ ] **Step 1: 새 캐시 버전을 요구하는 실패 테스트 작성**

```python
def test_background_loading_row_release_bumps_service_worker_cache():
    source = SW_JS.read_text(encoding="utf-8")
    assert 'const CACHE_NAME = "2026.08.02.1";' in source
```

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/test_frontend_guidelines.py -k background_loading_row_release_bumps -v`

Expected: FAIL with the previous cache version `2026.08.01.31`.

- [ ] **Step 3: 캐시 버전 증가**

```javascript
const CACHE_NAME = "2026.08.02.1";
```

- [ ] **Step 4: 전체 검증**

Run: `pytest -q`

Expected: all tests PASS.

- [ ] **Step 5: 캐시 변경 커밋 및 푸시**

```bash
git add static/sw.js tests/test_frontend_guidelines.py
git commit -m "배포: 백그라운드 상태 UI 캐시 갱신"
git push origin main
```
