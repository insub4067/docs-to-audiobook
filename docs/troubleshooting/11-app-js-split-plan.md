# static/app.js 분리 작업 기록 (진행 중)

## 상태
- 브랜치: `main`
- 1차 분리 완료: `toast.js`, `utils.js`, `db.js`, `auth.js`, `pwa.js`, `notifications.js`
- 2차 안전 모듈 분리 완료: `generation-status.js`, `voices.js`, `web-speech.js`, `reader-controls.js`
- 생성 워크플로 분리 완료: `generation.js`가 파일·URL 추출, 생성 설정, 로그인 예약 생성을 소유
- 현재 `static/app.js`: 1,871줄
- 다음 범위: 보관함 → 리더 본체 순서로 컨트롤러화
- 최신 설계: `docs/superpowers/specs/2026-08-02-app-js-phase-two-design.md`
- 최신 실행 계획: `docs/superpowers/plans/2026-08-02-app-js-generation-module.md`

## 왜 이렇게 결정했는가
`static/app.js`(3550줄)는 최상위 유틸 함수 4개만 빼고 전부 **하나의**
`document.addEventListener("DOMContentLoaded", async () => { ... })` 클로저 안에 있다.
그 안에서 DOM 요소 참조(`dropzone`, `readerAudio`, `audioList` 등)와 상태 변수(`currentTextId`, `db`,
`currentAudioObject` 등)를 수십 개 함수가 클로저로 공유한다. 업로드→생성→보관함→리더 흐름은
이 공유 상태에 깊이 얽혀 있어 억지로 분리하면 함수 시그니처를 대량으로 바꿔야 하고,
동작을 검증할 자동 테스트가 없어(문자열 패턴 검사뿐, `tests/test_frontend_guidelines.py`) 위험이 크다.
반면 인증 블록, 유틸 함수, IndexedDB 모듈, PWA 관련 코드는 이미 자기 완결적이라(자체적으로
`document.getElementById` 호출) 안전하게 뗄 수 있다는 걸 전체 파일을 다 읽고 확인했다.

## 핵심 기술 결정: ES 모듈이 아니라 "클래식 스크립트 + 전역 스코프 공유"

**ES 모듈(`type="module"`, import/export)을 쓰지 않는다.** 대신 새 파일들을
`<script src="...">` (모듈 아님, 기존과 동일한 클래식 스크립트)로 `app.js`보다 먼저 로드해서,
지금과 똑같이 "하나의 공유 전역 스코프"를 유지한다.

이렇게 하면:
- 새 파일로 옮기는 함수/변수는 **전역 선언**이 되고, `app.js`에 남는 코드에서 그 이름을 그냥
  호출하면(`initializeAuth()`, `getAllAudiobooksFromDB()` 등) 스코프 체인을 타고 전역에서
  찾아지므로 **호출부 코드를 단 한 글자도 안 바꿔도 된다.**
- 지금 파일 안에서 함수 선언 순서/클로저 참조가 이미 이렇게(자유 식별자 → 상위 스코프 탐색) 동작하고
  있으므로, 전역 스코프로 옮기는 것은 정확히 같은 동작을 재현한다. ES 모듈처럼 export/import를
  일일이 추가할 필요가 없어 실수 여지가 극적으로 줄어든다.

**단, 두 군데는 예외 처리가 필요하다** (이미 존재하는 패턴을 재사용):
- `app.js`에 남는 `syncWithCloud`, `renderLibrary`는 **클로저 로컬** 함수라 전역에서 안 보인다.
  기존 코드가 이미 `window.__syncAudiobooksToCloud = syncWithCloud;` (app.js 1867번째 줄 부근)로
  이 문제를 해결해 놓았다 — pwa.js의 pull-to-refresh(`runRefresh`)가 `syncWithCloud()`/`renderLibrary()`를
  직접 호출해야 하므로, 같은 패턴으로 `window.__renderLibrary = renderLibrary;` 한 줄을 추가하고
  pwa.js 쪽 호출을 `window.__syncAudiobooksToCloud()` / `window.__renderLibrary()`로 바꾼다.
- `db`(IndexedDB 핸들) 변수는 지금 app.js 클로저 안(354번째 줄 `let db = null;`)에 있는데,
  이걸 db.js로 옮기고 db.js 최상단에 `let db = null;`을 새로 선언한다(전역이 됨). app.js에서는
  이 한 줄만 지우면 되고, `saveAudiobookToDB` 등 db.js 안의 함수들이 내부적으로 이 전역 `db`를
  쓰므로 app.js의 호출부(`saveAudiobookToDB(entry)` 등)는 손댈 필요 없다.

## 정확한 라인 범위 (2026-08-01 기준 static/app.js, 3550줄)

아래 범위를 잘라서 각 파일로 옮긴다. **범위는 이 문서 작성 시점 기준이며, 실행 전 반드시
`grep -n` 등으로 현재 라인 번호를 재확인할 것** (다른 세션이 먼저 손댔을 수 있음).

### static/js/utils.js (신규)
- 1–24행: `escapeHtml`, `getAudiobookDisplayTitle`, `syncUrlClearButton`, `getReaderScrollTarget`
  (이미 최상위라 그대로 이동, 위험 없음)
- 2221–2227행: `formatBytes` (순수 함수, 의존성 없음)
- 2634–2640행: `// Time Formatter` 주석 + `formatTime` (순수 함수, 의존성 없음)

### static/js/toast.js (신규)
- 2267–2292행: `// Toast Notification System` 주석, `let toastTimeout = null;`, `showToast()`
- `showToast`는 `toast`/`toastIcon`/`toastMessage`/`readerOverlay` DOM을 참조하므로 toast.js
  최상단에 **자체적으로** `document.getElementById(...)`로 다시 조회해야 한다(중복 조회는 안전함,
  기존 app.js 쪽 동일 id 참조와 병행 가능).
- db.js/auth.js/pwa.js 전부 `showToast`를 호출하므로 **가장 먼저 로드**되어야 한다(또는 db.js보다
  먼저).

### static/js/db.js (신규)
- 최상단에 `let db = null;` 새로 선언 (app.js 354행의 것을 대체)
- 646–731행: `// 0. IndexedDB Utility Module` 주석부터 `updateAudiobookPosition` 끝까지
  (`initDB`, `saveAudiobookToDB`, `getAllAudiobooksFromDB`, `deleteAudiobookFromDB`,
  `updateAudiobookPosition`)
- 1335–1343행: `getAudiobookFromDB` (별도 위치, db.js 끝에 이어붙임)
- `initDB`가 실패 시 `showToast` 호출 → toast.js가 먼저 로드되어야 함

### static/js/pwa.js (신규)
- 372–498행: 당겨서 새로고침(pull-to-refresh) 블록.
  **수정 필요**: `runRefresh()` 안의 `syncWithCloud()` → `window.__syncAudiobooksToCloud()`,
  `renderLibrary()` → `window.__renderLibrary()`로 변경 (위 "예외 처리" 참고).
  `isLoggedIn()`은 auth.js가 전역으로 제공하므로 그대로 둬도 됨.
- 500–563행: 배포 업데이트 감지 블록 (`fetchBuildId`, `checkAndReloadIfUpdated`,
  `visibilitychange`/`scroll` 리스너). `showToast` 사용.
- 733–750행: sw.js 버전 표시 블록. **원본은 `appVersionDisplay`를 app.js 상단 DOM 블록(57행)의
  클로저 변수로 참조하는데, pwa.js로 옮기면 그 변수가 안 보이므로 pwa.js 안에서
  `const appVersionDisplay = document.getElementById("appVersionDisplay");`를 새로 선언해야 한다.**
  app.js 57행의 원래 선언은 다른 곳에서 안 쓰이는 걸 확인했으니 그냥 지운다(미사용 변수 방치 금지).
- 3081–3109행: `// iOS PWA Install Prompt` 주석 + `initIosPwaPrompt` 함수. 호출부(3111행,
  `initIosPwaPrompt();`)는 **app.js에 그대로 남긴다** (전역 함수 호출이라 그대로 동작).

### static/js/auth.js (신규)
- 3112–3549행: `// Authentication System` 주석부터 `showAuthError` 함수 끝까지 전부 통째로
  (파일 마지막 줄 3550 `});`는 DOMContentLoaded 클로저를 닫는 코드라 **반드시 app.js에 남겨야 함**,
  자르지 말 것).
- 이 블록은 이미 자체적으로 DOM을 조회해서 거의 수정 없이 그대로 옮기면 됨. 내부에서
  `getAllAudiobooksFromDB()`(db.js), `window.__syncAudiobooksToCloud`(app.js, 이미 window로 노출됨)를
  호출하는데 둘 다 위 전역 스코프 공유 방식으로 문제없이 동작함.
- 로드 순서상 auth.js는 db.js보다 뒤에 두는 게 안전(canStartAnonymousTrial이 getAllAudiobooksFromDB
  호출) — 실제로는 함수 "정의" 시점이 아니라 "호출" 시점에만 전역에 존재하면 되므로 스크립트
  로드 순서는 크게 중요하지 않지만, 명확성을 위해 순서를 지킨다.

### static/app.js에 남기는 것 (그대로 유지, 손대지 않음)
업로드/생성/보관함/리더 전체 로직 + 아래 두 군데만 수정:
1. 354행 `let db = null;` 삭제
2. 57행 `const appVersionDisplay = document.getElementById("appVersionDisplay");` 삭제
3. 1867행 `window.__syncAudiobooksToCloud = syncWithCloud;` 바로 다음 줄에
   `window.__renderLibrary = renderLibrary;` 추가
4. 파일 맨 앞(1–26행, utils 4개 함수 + 빈 줄)과 맨 위 IndexedDB 블록(646–751행 부근),
   Toast 블록(2267–2292행 부근), formatBytes/formatTime, iOS PWA 함수, Authentication 블록을
   위 계획대로 제거

## static/index.html 수정
`<script src="/static/app.js"></script>` (390행 부근) **바로 앞에** 새 스크립트 태그들을
**이 순서로** 추가한다 (module 아님, 기존과 동일한 일반 script):
```html
<script src="/static/js/toast.js"></script>
<script src="/static/js/utils.js"></script>
<script src="/static/js/db.js"></script>
<script src="/static/js/auth.js"></script>
<script src="/static/js/pwa.js"></script>
<script src="/static/app.js"></script>
```

## tests/test_frontend_guidelines.py 수정 필요 (중요, 안 고치면 CI 깨짐)
이 테스트 파일은 `APP_JS = ROOT_DIR / "static" / "app.js"`를 **직접 문자열 검사**한다.
분리 후 아래 항목들이 옮겨간 파일을 가리키도록 고쳐야 한다:

- `test_modals_support_escape_and_restore_focus`: `rememberModalFocus`/`restoreModalFocus`는
  **app.js에 그대로 남는다** (리더/액션시트 등 core 로직 소속) → 수정 불필요.
- `test_anonymous_trial_uses_a_private_session_header_and_one_time_marker`:
  `X-Anonymous-Session`, `anonymousTrialUsed`, `anonymousTrialInProgress` → `anonymousSessionHeaders`는
  auth.js로 이동하지만 `anonymousTrialUsed`/`anonymousTrialInProgress`는 app.js의
  `generateAudiobook`/`canStartAnonymousTrial` 양쪽에 걸쳐 있음 (`canStartAnonymousTrial`은
  auth.js로 이동, `generateAudiobook`은 app.js에 남음) → **두 파일 모두 읽어서 검사하도록 고쳐야 함**.
- `test_login_does_not_access_database_before_it_initializes`:
  `source.index("await initializeAuth();") < source.index("let db = null;")` 이 순서 비교는
  **분리 후 의미가 없어진다** (initializeAuth는 app.js에서 여전히 호출되지만 정의는 auth.js로
  이동, db 선언은 db.js로 이동). 이 테스트의 의도(로그인 확인이 DB 초기화보다 먼저 시작돼야
  한다)는 지금처럼 소스 문자열 위치 비교 대신, **app.js 안에서 `await initializeAuth();` 호출이
  `initDB()` 호출보다 앞에 있는지**로 바꿔서 검증해야 한다(둘 다 app.js에 남으므로).
  `"if (loggedIn && db) syncWithCloud();" not in source` / `"if (isLoggedIn()) syncWithCloud();" in source`
  부분은 app.js 그대로 유지되므로 app.js만 봐도 됨.
- `test_profile_menu_can_be_closed_outside_or_with_escape`,
  `test_profile_badge_uses_a_short_name_instead_of_google_avatar`,
  `test_admin_users_have_menu_and_triple_tap_entry_points` (일부):
  `setupAuthEventListeners`/`showAppUI` 내용 → **auth.js로 이동**, `STATIC_DIR/js/auth.js`를
  읽도록 고쳐야 함. 단 `adminDashboardLink.hidden = !isAdmin;`는 showAppUI 안(auth.js),
  `if (logoTapCount === 3) window.location.assign("/admin");`도 setupAuthEventListeners
  안(auth.js) → 둘 다 auth.js로.
- `test_url_fetch_button_shows_a_spinner_while_loading`, `test_library_syncs_playback_and_can_edit_titles`:
  해당 코드는 app.js에 그대로 남음 → 수정 불필요.

**작업 순서 권장**: 위 라인 범위대로 파일을 다 옮긴 뒤, `python3 -m pytest tests/test_frontend_guidelines.py -q`를
돌려서 무엇이 깨지는지 보고 하나씩 파일 경로를 고치는 게 제일 빠르고 정확하다(추측하지 말 것).

## 검증 절차 (구현 완료 후 반드시 수행)
1. `python3 -m pytest -q` 전체 그린 확인 (특히 test_frontend_guidelines.py)
2. 브라우저(Claude_Browser preview 도구)로 실제 로컬 서버 띄워서:
   - 파일 업로드 → 미리보기 → 생성 → 보관함 저장까지 한 번 실행
   - 로그인/로그아웃 (구글 소셜 로그인 버튼이 뜨는지, 클릭 시 정상 동작하는지)
   - 보관함에서 오디오 재생(리더 모드 진입), 재생/일시정지, 목차, 공유 버튼
   - 스와이프 삭제, 액션시트(더보기) 메뉴
   - 당겨서 새로고침(pull-to-refresh) — 이번에 window.__renderLibrary 브릿지로 바꾼 부분이라
     **특히 주의해서 확인**
   - 페이지를 백그라운드로 보냈다가 복귀 시 배포 업데이트 감지 로직이 에러 없이 도는지
     (콘솔에 ReferenceError 없는지 확인)
   - 콘솔에 `ReferenceError`/`is not defined` 없는지 반드시 확인 — 이게 이번 리팩터링에서
     가장 흔한 실패 유형이다(전역 스코프 공유가 깨지면 이런 형태로 터진다)
3. `static/sw.js`의 `CACHE_NAME`을 버전업한 뒤 커밋 (정적 자산 변경이므로 기존 메모리 규칙 적용)
4. 확인되면 `refactor/split-app-js` 브랜치를 main으로 머지 + 푸시 (사용자에게 먼저 확인받을 것 —
   이 저장소는 main 푸시 시 자동 배포됨)

## 다음 작업
보관함·클라우드 동기화와 리더 본체는 결합도가 높아 승인된 2차 설계에 따라 별도 TDD 배치로 순차 분리한다. 로컬/공유 리더의 중복 제거는 책임 이동과 섞지 않는다.
