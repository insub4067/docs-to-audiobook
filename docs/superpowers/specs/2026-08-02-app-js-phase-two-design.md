# `static/app.js` 2차 분리 설계

## 목적

`static/app.js`에 남아 있는 업로드·생성·보관함·리더 책임을 동작 변경 없이 분리한다. 최종적으로 `app.js`는 인증 이후 DOM과 공유 상태를 준비하고 각 컨트롤러를 초기화하는 부트스트랩 역할만 담당한다.

이번 작업은 기능 추가나 UI 변경이 아니다. 기존 API 요청, IndexedDB 스키마, 인증 흐름, 오디오 재생 동작, 토스트 문구를 유지한다.

## 현재 상태

- `app.js`: 2,740줄
- 1차 분리 완료: `auth.js`, `db.js`, `pwa.js`, `toast.js`, `utils.js`, `notifications.js`
- 남은 코드는 하나의 `DOMContentLoaded` 클로저에서 DOM 참조와 상태를 공유한다.
- 기존 `docs/troubleshooting/11-app-js-split-plan.md`의 브랜치 및 미완료 표시는 현재 저장소 상태와 맞지 않는다.

## 선택한 접근법

클래식 스크립트 로딩 방식은 유지하되, 숨은 전역 변수를 늘리지 않는다. 각 파일은 `window.TextAudio`에 컨트롤러 팩터리를 등록하고, `app.js`가 만든 명시적 컨텍스트를 받아 초기화한다.

```javascript
const appContext = {
    elements,
    state,
    services: {},
};

appContext.services.reader = TextAudio.createReaderController(appContext);
appContext.services.library = TextAudio.createLibraryController(appContext);
appContext.services.generation = TextAudio.createGenerationController(appContext);
```

`state`는 현재 문서, 업로드 파일, 재생 중인 오디오처럼 여러 책임이 실제로 공유하는 값만 포함한다. DOM 요소는 `elements`에 모으고, 한 모듈에서만 사용하는 DOM과 내부 상태는 해당 컨트롤러가 소유한다. 컨트롤러 사이 호출은 `context.services`를 통하며 자유 식별자에 의존하지 않는다.

ES 모듈 전환은 하지 않는다. 현재 인증/PWA 스크립트와 인라인 초기화 방식까지 동시에 바꾸면 정적 파일 분리보다 변경 범위가 커지기 때문이다.

## 단계별 분리

### 1. 낮은 결합도 모듈

먼저 독립성이 높은 네 책임을 분리한다.

- `generation-status.js`: 생성 중 목록 행 생성·중복 방지·제거
- `voices.js`: 음성 목록, 설명, 미리듣기와 관련 내부 오디오 상태
- `web-speech.js`: Web Speech 대체 재생과 발화 상태
- `reader-controls.js`: 10초 이동, 반복, 재생 속도, 취침 타이머

`reader-controls.js`는 내부 반복·속도 상태를 직접 공개하지 않는다. 리더 본체에는 `getPlaybackSettings()`와 `clearSleepTimer()`만 제공한다.

### 2. 생성 컨트롤러

`generation.js`는 아래 흐름을 하나의 책임으로 소유한다.

- 파일 선택과 다중 파일 처리
- 서버 텍스트 추출과 미리보기 반영
- URL 기사 추출
- 속도·피치 설정
- 생성 모달과 생성 버튼 처리
- TTS/백그라운드 생성 요청

파일 업로드와 생성 요청을 별도 모듈로 먼저 나누지 않는다. `currentTextId`, 접근 토큰, 업로드 파일, 생성 설정이 한 흐름에서 함께 바뀌기 때문이다.

외부 의존성은 다음 계약으로 제한한다.

- `services.library.refresh()`
- `services.library.sync()`
- `services.generationStatus.show()/remove()`
- 로그인 유도 함수
- `window.__requestPushNotificationSubscription()`

알림 등록 실패는 현재처럼 오디오북 생성을 중단하지 않는다.

### 3. 보관함 컨트롤러

`library.js`는 첫 이동 단계에서 다음을 함께 소유한다.

- 기본 제공 오디오북 시드
- IndexedDB 목록 렌더링
- 클라우드 업로드·다운로드·동기화
- 재생 위치 저장·복원
- 액션시트, 공유, 다운로드, 제목 편집, 삭제

초기 이동에서 `cloud.js`를 별도로 만들지 않는다. 현재 `renderLibrary → ensureAudioData → syncWithCloud → renderLibrary` 호출 관계를 먼저 한 모듈 안에 유지한 뒤, 렌더링과 동기화의 순환이 제거된 경우에만 후속 작업으로 나눈다.

외부에는 `refresh`, `sync`, `savePlaybackState`, `fetchPlaybackState`와 필요한 액션만 공개한다.

### 4. 리더 컨트롤러

`reader.js`는 마지막에 이동한다.

- 로컬 오디오북 리더
- 공유 링크 리더
- 문장 렌더링과 현재 문장 강조
- 자동 스크롤
- 목차
- 재생/일시정지와 진행률
- 리더 UI 자동 숨김과 스와이프 닫기

현재 코드를 그대로 이동하며 로컬/공유 리더의 중복 제거는 하지 않는다. 공통 렌더러 추출은 이번 분리 범위에서 제외한다.

### 5. 부트스트랩 정리

모든 컨트롤러가 준비되면 `app.js`에는 다음만 남긴다.

- `DOMContentLoaded`
- 인증 초기화
- 공용 DOM 및 공유 상태 생성
- 컨트롤러 생성 및 초기화 순서
- 지연된 로그인 후 생성 예약 처리
- 공유 링크 및 PWA/백그라운드 알림 초기화

## 초기화 순서

1. 인증 초기화
2. 공용 DOM 및 상태 생성
3. 낮은 결합도 서비스 생성
4. 리더 컨트롤러 생성
5. 보관함 컨트롤러 생성
6. 생성 컨트롤러 생성
7. 이벤트 리스너 연결
8. DB 초기화와 최초 목록·공유 링크·PWA 초기화

컨트롤러 생성 중에는 네트워크 요청이나 목록 렌더링을 시작하지 않는다. 모든 서비스가 등록된 뒤 부트스트랩이 명시적으로 `initialize()`를 호출한다.

## 오류 처리

- 기존 사용자 노출 토스트와 실패 복구 동작을 유지한다.
- 컨트롤러가 없어도 조용히 넘어가는 선택적 호출을 새로 만들지 않는다. 필수 서비스 누락은 개발 단계에서 즉시 실패해야 한다.
- Object URL, 타이머, 음성 미리듣기처럼 생명주기가 있는 자원은 해당 컨트롤러가 정리한다.
- 기존 `window.__syncAudiobooksToCloud`, `window.__renderLibrary`, 생성 상태 브리지는 외부 스크립트 호환을 위해 유지하되 내부 구현으로 전달한다.

## 테스트 전략

각 단계는 테스트 우선으로 진행한다.

1. 이동 대상의 현재 행위를 Node VM 특성화 테스트로 고정한다.
2. 새 파일 로드와 공개 계약을 검증하는 테스트를 먼저 실패시킨다.
3. 최소 이동으로 테스트를 통과시킨다.
4. 기존 소스 위치 기반 테스트가 새 책임 파일을 실행하도록 변경한다.
5. 단계마다 `tests/test_frontend_guidelines.py`와 전체 `pytest`를 실행한다.

반드시 보호할 행위:

- 생성 진행 행은 작업 ID당 하나만 존재하고 완료 시 제거된다.
- 음성 미리듣기는 새 재생과 모달 닫기에서 기존 오디오를 정리한다.
- 알림 구독 실패와 관계없이 생성 요청은 계속된다.
- 보관함 동시 렌더가 항목을 중복하지 않는다.
- 리더의 현재 문장 강조와 자동 스크롤이 재생 위치를 따른다.
- 반복·속도·타이머 설정이 리더 재개 후에도 유지된다.
- 공유 링크와 로컬 리더가 모두 열린다.

마지막 검증은 다음을 포함한다.

- 전체 `pytest -q`
- 정적 스크립트 로드 순서와 Service Worker 프리캐시 확인
- 브라우저에서 업로드 → 미리보기 → 생성 → 보관함 → 리더 재생
- 로그인/로그아웃, 공유 링크, 액션시트, 당겨서 새로고침
- 콘솔 `ReferenceError` 및 초기화 순서 오류 확인

## 배포 및 커밋

- 각 단계는 독립적인 한국어 커밋으로 기록한다.
- 새 정적 스크립트는 `static/index.html`과 `static/sw.js` 프리캐시에 추가한다.
- 모든 프런트 변경이 완료된 뒤 `CACHE_NAME`을 한 번 올린다.
- 전체 검증 후 `main`에 직접 푸시한다.

## 완료 기준

- `app.js`가 부트스트랩 중심 파일이 된다.
- 업로드·생성·보관함·리더 책임이 명시적 컨트롤러로 분리된다.
- 새 모듈 간 의존성이 `context.services` 계약으로 드러난다.
- 기존 사용자 동작과 서버 API 계약이 바뀌지 않는다.
- 모든 자동 테스트와 브라우저 핵심 흐름 검증이 통과한다.
