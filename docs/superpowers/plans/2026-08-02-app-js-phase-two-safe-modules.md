# `static/app.js` 2차 안전 모듈 분리 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `static/app.js`에서 생성 상태 UI, 음성 선택, Web Speech, 리더 보조 컨트롤을 동작 변경 없이 독립 파일로 분리한다.

**Architecture:** 기존 클래식 스크립트 로딩을 유지하고 각 파일이 `window.TextAudio`에 팩터리 함수를 등록한다. `app.js`는 현재 DOM 요소와 브라우저 의존성을 팩터리에 전달하며, 반환된 컨트롤러의 명시적 메서드만 사용한다.

**Tech Stack:** Vanilla JavaScript, Service Worker precache, pytest, Node `vm`

## Global Constraints

- API, IndexedDB, 인증, UI 문구와 사용자 동작을 바꾸지 않는다.
- 테스트를 먼저 실패시킨 뒤 최소 구현으로 통과시킨다.
- 새 스크립트는 `static/index.html`에서 `static/app.js`보다 먼저 로드한다.
- 새 스크립트는 `static/sw.js` 프리캐시에 포함한다.
- 모든 프런트 변경 후 `CACHE_NAME`을 현재 `2026.08.02.2`에서 `2026.08.02.3`으로 증가시킨다.
- 각 단계는 한국어 커밋으로 기록한다.

---

### Task 1: 생성 진행 상태 컨트롤러

**Files:**
- Create: `static/js/generation-status.js`
- Modify: `static/app.js:845-889`
- Modify: `static/index.html:394-400`
- Modify: `tests/test_frontend_guidelines.py:1-105`

**Interfaces:**
- Consumes: `{ audioList: HTMLElement, libraryEmpty: HTMLElement }`
- Produces: `TextAudio.createGenerationStatusController(dependencies) -> { show(jobId, title), remove(jobId) }`
- Preserves: `window.__showBackgroundJobLoading`, `window.__removeBackgroundJobLoading`

- [ ] **Step 1: 새 컨트롤러 행위 실패 테스트 작성**

`GENERATION_STATUS_JS` 경로를 추가하고 Node VM에서 파일을 실행한다. 동일 작업 ID를 두 번 `show()`해도 한 행만 생성되고 `remove()` 후 빈 상태가 보이는지 검증한다.

```javascript
vm.runInNewContext(source, context);
const controller = context.window.TextAudio.createGenerationStatusController({ audioList, libraryEmpty });
const first = controller.show("job-1", "첫 번째.mp3");
const duplicate = controller.show("job-1", "중복.mp3");
if (first !== duplicate || audioList.children.length !== 1) throw new Error("중복 생성");
controller.remove("job-1");
if (audioList.children.length !== 0 || libraryEmpty.style.display !== "flex") throw new Error("제거 실패");
```

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/test_frontend_guidelines.py -k generation_status_controller -v`

Expected: FAIL because `static/js/generation-status.js` does not exist.

- [ ] **Step 3: 최소 구현과 연결**

기존 네 함수를 컨트롤러 내부로 이동한다. `app.js`에서는 다음처럼 인스턴스를 만들고 기존 호출 이름을 유지한다.

```javascript
const generationStatus = TextAudio.createGenerationStatusController({ audioList, libraryEmpty });
const showBackgroundJobLoading = generationStatus.show;
const removeBackgroundJobLoading = generationStatus.remove;
window.__showBackgroundJobLoading = showBackgroundJobLoading;
window.__removeBackgroundJobLoading = removeBackgroundJobLoading;
```

`index.html`에 `/static/js/generation-status.js`를 `app.js`보다 먼저 추가한다.

- [ ] **Step 4: 대상 테스트 통과 확인**

Run: `pytest tests/test_frontend_guidelines.py -k 'generation_status_controller or background_loading_row' -v`

Expected: PASS.

- [ ] **Step 5: 커밋**

```bash
git add static/js/generation-status.js static/app.js static/index.html tests/test_frontend_guidelines.py
git commit -m "리팩터링: 생성 진행 상태를 app.js에서 분리"
```

### Task 2: 음성 선택과 미리듣기 컨트롤러

**Files:**
- Create: `static/js/voices.js`
- Modify: `static/app.js:16-18,354-472`
- Modify: `static/index.html:394-401`
- Modify: `tests/test_frontend_guidelines.py`

**Interfaces:**
- Consumes: `{ voiceSelect, voiceDesc, voicePreviewBtn, voicePreviewLabel, fetch, createAudio, createObjectURL, notify }`
- Produces: `TextAudio.createVoiceController(dependencies) -> { initialize(), loadVoices(), stopPreview(), getSelectedVoice() }`

- [ ] **Step 1: 음성 컨트롤러 실패 테스트 작성**

Node VM 테스트에서 서버 음성 목록을 반환하고 `loadVoices()` 뒤 옵션과 설명이 갱신되는지 검증한다. 미리듣기 버튼을 두 번 누르면 첫 번째 오디오가 정지되고 라벨이 `미리듣기`로 복원되는지 검증한다.

```javascript
const controller = context.window.TextAudio.createVoiceController(dependencies);
controller.initialize();
await controller.loadVoices();
if (voiceSelect.children.length !== 1 || voiceDesc.textContent !== "차분함") throw new Error("음성 목록 실패");
await voicePreviewBtn.click();
await voicePreviewBtn.click();
if (pauseCount !== 1 || voicePreviewLabel.textContent !== "미리듣기") throw new Error("미리듣기 정리 실패");
```

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/test_frontend_guidelines.py -k voice_controller -v`

Expected: FAIL because `static/js/voices.js` does not exist.

- [ ] **Step 3: 최소 구현과 연결**

음성 관련 DOM 및 `availableVoices`, `previewAudio`를 컨트롤러 내부로 이동한다. `closeGenerationModal()`은 `voiceController.stopPreview()`를 호출하며, 부트스트랩은 `voiceController.initialize()` 후 `voiceController.loadVoices()`를 호출한다. 생성 요청의 음성 값은 `voiceController.getSelectedVoice()`를 사용한다.

- [ ] **Step 4: 대상 및 프런트 테스트 확인**

Run: `pytest tests/test_frontend_guidelines.py -k 'voice_controller or generation_requests_completion_notification' -v`

Expected: PASS.

- [ ] **Step 5: 커밋**

```bash
git add static/js/voices.js static/app.js static/index.html tests/test_frontend_guidelines.py
git commit -m "리팩터링: 음성 선택을 app.js에서 분리"
```

### Task 3: Web Speech 컨트롤러

**Files:**
- Create: `static/js/web-speech.js`
- Modify: `static/app.js:1920-1955,2477-2485`
- Modify: `static/index.html:394-402`
- Modify: `tests/test_frontend_guidelines.py`

**Interfaces:**
- Consumes: `{ speechSynthesis, createUtterance, notify }`
- Produces: `TextAudio.createWebSpeechController(dependencies) -> { speak(text, voice, rate, pitch), stop() }`

- [ ] **Step 1: Web Speech 실패 테스트 작성**

`speak()`이 기존 발화를 취소하고 한국어 발화를 재생하며, `stop()`이 다시 취소하는지 Node VM으로 검증한다. 지원하지 않는 경우 오류 토스트가 한 번 발생해야 한다.

```javascript
const controller = context.window.TextAudio.createWebSpeechController(dependencies);
controller.speak("본문", "ko-KR", 1.25, 1.0);
if (spoken.length !== 1 || spoken[0].text !== "본문" || cancelCount !== 1) throw new Error("발화 실패");
controller.stop();
if (cancelCount !== 2) throw new Error("정지 실패");
```

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/test_frontend_guidelines.py -k web_speech_controller -v`

Expected: FAIL because `static/js/web-speech.js` does not exist.

- [ ] **Step 3: 최소 구현과 연결**

기존 Web Speech 함수와 내부 상태를 컨트롤러로 이동한다. `app.js`에서 `webSpeechController.speak(...)`와 `webSpeechController.stop()`으로 두 호출부만 교체한다.

- [ ] **Step 4: 대상 테스트 통과 확인**

Run: `pytest tests/test_frontend_guidelines.py -k web_speech_controller -v`

Expected: PASS.

- [ ] **Step 5: 커밋**

```bash
git add static/js/web-speech.js static/app.js static/index.html tests/test_frontend_guidelines.py
git commit -m "리팩터링: Web Speech를 app.js에서 분리"
```

### Task 4: 리더 보조 컨트롤러

**Files:**
- Create: `static/js/reader-controls.js`
- Modify: `static/app.js:1456-1457,1979-1982,2133,2236-2237,2255-2266,2448,2580-2719`
- Modify: `static/index.html:394-403`
- Modify: `tests/test_frontend_guidelines.py`

**Interfaces:**
- Consumes: `{ readerAudio, skipBackBtn, skipForwardBtn, repeatBtn, repeatText, speedBtn, speedText, timerBtn, timerText, storage, notify, setInterval, clearInterval }`
- Produces: `TextAudio.createReaderControls(dependencies) -> { initialize(), getPlaybackSettings(), applyPlaybackSettings(settings), clearSleepTimer() }`
- `getPlaybackSettings()` returns `{ playbackSpeed: number, repeatMode: "off" | "all" | "one" }`.
- `applyPlaybackSettings({ playbackSpeed, repeatMode })` ignores unsupported values and applies supported values to UI/audio.

- [ ] **Step 1: 리더 컨트롤 실패 테스트 작성**

Node VM에서 저장된 속도·반복 모드 초기화, 10초 이동 경계, 속도/반복 순환, 타이머 해제를 검증한다.

```javascript
const controls = context.window.TextAudio.createReaderControls(dependencies);
controls.initialize();
if (controls.getPlaybackSettings().playbackSpeed !== 1.25) throw new Error("저장 속도 복원 실패");
skipBackBtn.click();
if (readerAudio.currentTime !== 0) throw new Error("뒤로 이동 경계 실패");
controls.applyPlaybackSettings({ playbackSpeed: 1.5, repeatMode: "one" });
if (readerAudio.playbackRate !== 1.5 || controls.getPlaybackSettings().repeatMode !== "one") throw new Error("설정 적용 실패");
```

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/test_frontend_guidelines.py -k reader_controls -v`

Expected: FAIL because `static/js/reader-controls.js` does not exist.

- [ ] **Step 3: 최소 구현과 호출부 교체**

리더 보조 상태와 이벤트를 컨트롤러로 이동한다. 기존 직접 배열/인덱스 접근은 다음 계약으로 바꾼다.

```javascript
const { playbackSpeed, repeatMode } = readerControls.getPlaybackSettings();
readerControls.applyPlaybackSettings({
    playbackSpeed: audio.playbackSpeed,
    repeatMode: audio.repeatMode,
});
readerControls.clearSleepTimer();
```

- [ ] **Step 4: 대상 및 프런트 테스트 통과 확인**

Run: `pytest tests/test_frontend_guidelines.py -k 'reader_controls or playback or reader' -v`

Expected: PASS.

- [ ] **Step 5: 커밋**

```bash
git add static/js/reader-controls.js static/app.js static/index.html tests/test_frontend_guidelines.py
git commit -m "리팩터링: 리더 보조 컨트롤을 app.js에서 분리"
```

### Task 5: 정적 자산 등록과 배치 검증

**Files:**
- Modify: `static/sw.js:1-20`
- Modify: `tests/test_frontend_guidelines.py:16-30,883-890`
- Modify: `docs/troubleshooting/11-app-js-split-plan.md`

**Interfaces:**
- Consumes: 네 신규 정적 스크립트 경로
- Produces: 새 `CACHE_NAME`, 정확한 프리캐시·HTML 로드 순서, 최신 분리 상태 문서

- [ ] **Step 1: 정적 자산 실패 테스트 작성**

`SPLIT_APP_SCRIPTS`에 네 파일을 추가하고 HTML에서 모두 `app.js`보다 먼저 로드되며 `sw.js` 프리캐시에 포함되는지 검증한다. 캐시 버전은 `2026.08.02.3`으로 고정한다.

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/test_frontend_guidelines.py -k 'split_app_scripts or service_worker_precaches' -v`

Expected: FAIL because the new assets are not yet all precached and the cache version is unchanged.

- [ ] **Step 3: 프리캐시·버전·문서 갱신**

네 파일을 `ASSETS_TO_CACHE`에 추가하고 `CACHE_NAME`을 `2026.08.02.3`으로 올린다. 기존 문제 해결 문서는 1차 완료와 이번 안전 모듈 분리 결과, 아직 남은 생성·보관함·리더 본체 범위를 반영한다.

- [ ] **Step 4: 전체 검증**

Run: `pytest -q`

Expected: all tests PASS.

Run: `git diff --check`

Expected: exit 0.

- [ ] **Step 5: 커밋**

```bash
git add static/sw.js tests/test_frontend_guidelines.py docs/troubleshooting/11-app-js-split-plan.md
git commit -m "배포: app.js 안전 모듈 캐시 갱신"
```

### Task 6: 다음 배치 진입 조건 확인

**Files:**
- Create: `docs/superpowers/plans/2026-08-02-app-js-generation-module.md`

**Interfaces:**
- Consumes: 분리된 네 컨트롤러와 전체 테스트 결과
- Produces: `generation.js` 분리를 위한 별도 TDD 계획

- [ ] **Step 1: 현재 `app.js` 줄 수와 생성 영역 의존성 재계측**

Run: `wc -l static/app.js static/js/*.js`

Run: `rg -n 'currentTextId|currentTextAccessToken|uploadedFile|generateAudiobook|renderLibrary|syncWithCloud' static/app.js`

- [ ] **Step 2: 생성 모듈 계획 작성·자체 검토**

승인된 설계의 생성 컨트롤러 계약을 그대로 사용하고, 실제 변경 후 라인 기준으로 테스트·이동 범위와 완성된 인터페이스를 기록한다.

- [ ] **Step 3: 계획 커밋**

```bash
git add docs/superpowers/plans/2026-08-02-app-js-generation-module.md
git commit -m "계획: app.js 생성 워크플로 분리"
```
