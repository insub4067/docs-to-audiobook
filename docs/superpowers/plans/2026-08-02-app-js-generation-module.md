# `static/app.js` 생성 워크플로 모듈 분리 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 파일·URL 입력부터 텍스트 추출, 생성 설정, 오디오북 생성까지의 흐름을 `static/js/generation.js`로 옮겨 `app.js`의 공유 상태와 런타임 누락 위험을 줄인다.

**Architecture:** `generation.js`가 `TextAudio.createGenerationController(dependencies)`를 등록한다. 컨트롤러는 업로드된 텍스트 상태와 생성 이벤트를 소유하고, 보관함 저장·동기화·인증·모달·진행 행은 명시적으로 주입받는다. 기존 API, 문구, 로그인 체험 정책과 백그라운드 작업 동작은 바꾸지 않는다.

**Tech Stack:** Vanilla JavaScript, Service Worker precache, pytest, Node `vm`

## Global Constraints

- 동작 변경 없이 기존 코드를 수술적으로 이동한다.
- 실패 테스트를 먼저 추가하고 최소 구현으로 통과시킨다.
- `generation.js`는 `app.js`보다 먼저 로드하고 서비스워커 프리캐시에 등록한다.
- 로그인 유도 예약 생성과 생성 완료 알림 요청을 유지한다.
- 프런트 변경을 모두 마친 뒤 `sw.js` 버전을 한 번 더 올린다.

### Task 1: 생성 컨트롤러 공개 계약 테스트

**Files:**
- Create: `static/js/generation.js`
- Modify: `tests/test_frontend_guidelines.py`

- [ ] `createGenerationController()`가 `initialize()`와 `runPendingGeneration()`을 제공하는 실패 테스트를 작성한다.
- [ ] 생성 버튼 클릭 시 알림 권한 요청 실패와 무관하게 생성 콜백이 실행되는 기존 특성을 컨트롤러 기준으로 검증한다.
- [ ] `pytest tests/test_frontend_guidelines.py -k generation_controller -q`가 신규 파일 부재로 실패하는지 확인한다.

### Task 2: 입력·추출·설정 흐름 이동

**Files:**
- Modify: `static/js/generation.js`
- Modify: `static/app.js`
- Modify: `static/index.html`
- Modify: `tests/test_frontend_guidelines.py`

- [ ] `currentTextId`, `currentTextAccessToken`, `uploadedFile`을 컨트롤러 내부 상태로 이동한다.
- [ ] 파일 선택·드래그앤드롭·배치·URL 추출·초기화·슬라이더 이벤트를 그대로 이동한다.
- [ ] 컨트롤러 `initialize()`에서 관련 이벤트를 한 번만 연결한다.
- [ ] URL 스피너, 파일 제한, 입력 초기화 특성 테스트가 새 파일을 검사하도록 바꾼다.

### Task 3: 생성·로그인 예약 흐름 이동

**Files:**
- Modify: `static/js/generation.js`
- Modify: `static/app.js`
- Modify: `tests/test_frontend_guidelines.py`

- [ ] `generateAudiobook`, 로그인 유도 액션시트, `pendingGeneration` 복원 코드를 컨트롤러로 이동한다.
- [ ] 전경 진행 행 생성, 백그라운드 작업 등록, 폴링, IndexedDB 저장, 보관함 렌더·동기화 호출을 주입된 계약으로 유지한다.
- [ ] 생성 버튼 알림 요청 실패 회귀 테스트와 예약 생성 실행 테스트를 통과시킨다.
- [ ] 이동 후 `app.js`에 생성 상태나 생성 함수 참조가 남지 않았는지 `rg`로 확인한다.

### Task 4: 정적 자산·문서·캐시 갱신

**Files:**
- Modify: `static/index.html`
- Modify: `static/sw.js`
- Modify: `docs/troubleshooting/11-app-js-split-plan.md`
- Modify: `tests/test_frontend_guidelines.py`

- [ ] `generation.js`가 `app.js`보다 먼저 로드되고 프리캐시에 포함되는 테스트를 추가한다.
- [ ] `sw.js` 캐시 버전을 다음 값으로 증가시킨다.
- [ ] 분리 현황 문서에 생성 워크플로 완료와 남은 보관함·리더 경계를 기록한다.

### Task 5: 전체 검증과 배포

- [ ] `node --check static/js/generation.js static/app.js`를 통과한다.
- [ ] `pytest tests/test_frontend_guidelines.py -q`를 통과한다.
- [ ] `pytest -q` 전체 테스트를 통과한다.
- [ ] 변경 파일과 diff를 검토하고 한국어 커밋을 만든다.
- [ ] `main`을 원격 저장소에 푸시한다.
