# 오디오북 생성 시 알림 권한 요청 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 로그인 사용자가 오디오북 생성을 누를 때 미구독 상태라면 iOS 알림 권한과 Push 구독을 요청하고, 결과와 무관하게 생성을 계속한다.

**Architecture:** `static/js/notifications.js`가 초기화 시 준비한 Push 설정과 구독 상태를 보관하고 `window.__requestPushNotificationSubscription()`으로 단일 “켜기” 동작을 제공한다. 프로필 토글과 `static/app.js`의 생성 버튼이 같은 함수를 사용하며 서버나 데이터베이스는 변경하지 않는다.

**Tech Stack:** Vanilla JavaScript, Service Worker Push API, pytest에서 실행하는 Node VM 프런트엔드 테스트

## Global Constraints

- 권한 요청은 오디오북 생성 버튼의 직접 사용자 제스처에서 시작한다.
- 이미 구독됨 또는 권한 차단 상태에서는 다시 요청하지 않는다.
- 알림 설정 실패 또는 미지원 환경에서도 오디오북 생성은 계속한다.
- 프로필 메뉴의 기존 구독 해제 동작은 유지한다.
- 프런트엔드 변경 후 `static/sw.js` 캐시 버전을 `2026.08.02.2`로 증가시킨다.

---

### Task 1: 공유 Push 구독 요청과 생성 흐름 연결

**Files:**
- Modify: `static/js/notifications.js:160-330`
- Modify: `static/app.js:815-835`
- Test: `tests/test_frontend_guidelines.py`

**Interfaces:**
- Consumes: 준비된 `config`, `registration`, 현재 `subscription`, `Notification.permission`
- Produces: `window.__requestPushNotificationSubscription() -> Promise<boolean>`

- [ ] **Step 1: 실패 테스트 작성**

기존 Push 시나리오 테스트에서 공개 함수를 호출해 다음 행위를 검증한다.

```javascript
const generated = await scenario("default", null);
const enabled = await generated.context.window.__requestPushNotificationSubscription();
if (!enabled || generated.counts().requestCount !== 1 || generated.counts().subscribeCount !== 1) {
  throw new Error("생성 시 알림 구독을 요청하지 않았습니다.");
}

const blocked = await scenario("denied", null);
if (await blocked.context.window.__requestPushNotificationSubscription()) {
  throw new Error("차단된 권한을 다시 요청했습니다.");
}
```

알림 서버 저장이 실패하는 시나리오는 함수가 `false`를 반환하며 예외를 밖으로 던지지 않는지 검증한다. `static/app.js`에는 생성 함수 전에 공개 알림 요청 함수를 기다리는 호출이 존재해야 한다.

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/test_frontend_guidelines.py -k 'push_button_initial_state or generation_requests_completion_notification' -v`

Expected: FAIL because `window.__requestPushNotificationSubscription` does not exist and generation does not call it.

- [ ] **Step 3: 최소 구현**

알림 초기화가 만든 상태를 모듈 범위에 저장하고 켜기 동작을 함수로 분리한다.

```javascript
let pushNotificationContext = null;

async function requestPushNotificationSubscription() {
    const context = pushNotificationContext;
    if (!context || context.subscriptionIsRegistered || Notification.permission === "denied") {
        return Boolean(context?.subscriptionIsRegistered);
    }
    try {
        const permissionRequest = Notification.permission === "granted"
            ? Promise.resolve("granted")
            : Notification.requestPermission();
        const permission = await permissionRequest;
        if (permission !== "granted") return false;
        const createdSubscription = !context.subscription;
        if (createdSubscription) {
            context.subscription = await context.registration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: urlBase64ToUint8Array(context.config.public_key),
            });
        }
        await savePushSubscription(context.subscription);
        context.subscriptionIsRegistered = true;
        localStorage.setItem(PUSH_SUBSCRIPTION_OWNER_KEY, getCurrentAuthenticatedUserId());
        renderPushNotificationState(context.button, context.label, "on");
        showToast("완료 알림 켜짐", "success");
        return true;
    } catch (error) {
        showToast("완료 알림 설정에 실패했습니다.", "error");
        return false;
    }
}
```

초기화 후 `window.__requestPushNotificationSubscription = requestPushNotificationSubscription`을 설정한다. 프로필 토글의 꺼짐 분기는 이 함수를 호출한다. 생성 버튼 처리기는 모달을 닫은 직후 다음을 실행한다.

```javascript
await window.__requestPushNotificationSubscription?.();
await generateAudiobook({
    textId: currentTextId,
    textAccessToken: currentTextAccessToken,
    filename: toAudioFilename(originalName),
    charCount: parseInt(charCountBadge.textContent.replace(/[^0-9]/g, "")) || 0,
    voice: voiceSelect.value,
    rate: getFormattedSpeed(parseInt(speedSlider.value)),
    pitch: getFormattedPitch(parseInt(pitchSlider.value)),
});
```

- [ ] **Step 4: 대상 테스트 통과 확인**

Run: `pytest tests/test_frontend_guidelines.py -k 'push_button_initial_state or generation_requests_completion_notification' -v`

Expected: PASS.

- [ ] **Step 5: 구현 커밋**

```bash
git add static/js/notifications.js static/app.js tests/test_frontend_guidelines.py
git commit -m "기능: 오디오북 생성 시 완료 알림 요청"
```

### Task 2: 캐시 갱신과 전체 회귀 검증

**Files:**
- Modify: `static/sw.js:1`
- Modify: `tests/test_frontend_guidelines.py`

**Interfaces:**
- Consumes: `CACHE_NAME`
- Produces: 캐시 버전 `2026.08.02.2`

- [ ] **Step 1: 실패 테스트 작성**

```python
def test_generation_push_permission_release_bumps_service_worker_cache():
    source = SW_JS.read_text(encoding="utf-8")
    assert 'const CACHE_NAME = "2026.08.02.2";' in source
```

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/test_frontend_guidelines.py -k generation_push_permission_release_bumps -v`

Expected: FAIL with cache version `2026.08.02.1`.

- [ ] **Step 3: 캐시 버전 증가**

```javascript
const CACHE_NAME = "2026.08.02.2";
```

- [ ] **Step 4: 전체 검증**

Run: `pytest -q`

Expected: all tests PASS.

- [ ] **Step 5: 커밋과 푸시**

```bash
git add static/sw.js tests/test_frontend_guidelines.py
git commit -m "배포: 생성 알림 권한 UI 캐시 갱신"
git push origin main
```
