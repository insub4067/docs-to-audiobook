# Task 1 구현 보고서 — static/app.js 안전 범위 분리

## 상태

DONE_WITH_CONCERNS

## 변경 파일

- `static/js/utils.js`: HTML 이스케이프, 표시 제목, URL 초기화 버튼, 리더 스크롤 계산, 바이트/시간 포맷 함수를 원본 동작 그대로 이동했다.
- `static/js/toast.js`: 토스트 DOM을 자체 조회하고 기존 `showToast` 구현을 이동했다.
- `static/js/db.js`: 전역 `db` 핸들과 IndexedDB 함수 6개를 이동했다.
- `static/js/auth.js`: `Authentication System` 블록 전체를 이동했다.
- `static/js/pwa.js`: 당겨서 새로고침, 배포 업데이트 감지, SW 버전 표시, iOS PWA 안내를 이동했다.
- `static/app.js`: 이동된 선언/정의를 제거하고 `window.__renderLibrary` 브리지를 추가했다. 업로드·생성·보관함·리더 핵심 로직과 DOMContentLoaded 닫힘은 유지했다.
- `static/index.html`: 클래식 스크립트를 `toast.js → utils.js → db.js → auth.js → pwa.js → app.js` 순으로 로드한다.
- `tests/test_frontend_guidelines.py`: 이동된 유틸/인증 정의를 새 파일에서 읽고, 인증 선행 검사는 `initializeAuth` 호출과 `initDB` 호출 순서를 비교하도록 수정했다.
- `static/sw.js`: `CACHE_NAME`을 `2026.08.01.27`로 올렸다.

## 핵심 판단

- ES module을 도입하지 않고 기존 클래식 스크립트의 전역 식별자 공유를 유지했다.
- 이동 본문은 원본과 대조해 들여쓰기만 제거했다. PWA 새로고침의 `syncWithCloud`/`renderLibrary` 호출만 계획대로 `window.__syncAudiobooksToCloud`/`window.__renderLibrary`로 바꿨다.
- `appVersionDisplay`는 `pwa.js`에서 직접 조회하고, `initIosPwaPrompt()` 호출은 `app.js`에 남겼다.
- 범위 밖인 업로드·생성·보관함·리더 로직은 추가 분리하거나 리팩터링하지 않았다.

## 테스트 결과

- RED: `.venv/bin/python -m pytest tests/test_frontend_guidelines.py -q` → 선행 미완성 상태에서 유틸 경로 관련 4건 실패를 확인했다.
- `node --check static/js/toast.js && node --check static/js/utils.js && node --check static/js/db.js && node --check static/js/auth.js && node --check static/js/pwa.js && node --check static/app.js` → 통과.
- `.venv/bin/python -m pytest tests/test_frontend_guidelines.py -q` → 20 passed.
- `.venv/bin/python -m pytest -q` → 132 passed, 174 warnings.
- `git diff --check` → 통과.

## 브라우저 검증

- 로컬 Uvicorn 서버에서 `/static/js/toast.js`, `utils.js`, `db.js`, `auth.js`, `pwa.js`, `app.js`가 모두 HTTP 200으로 로드되는 것을 확인했다.
- 기본 화면, Google 로그인 버튼, 음성 목록, 기본 오디오북, `v 2026.08.01.27` 표시를 확인했다.
- 기본 제공 오디오북을 눌러 리더 화면에 진입하고 제목·본문·재생 컨트롤이 렌더링되는 것을 확인했다.
- 초기 로드와 리더 진입 후 브라우저 콘솔 `error`/`warn`은 0건이었다.

## 우려사항

- 실제 OAuth 완료, 파일 업로드/생성, 터치 기반 pull-to-refresh, 백그라운드 복귀 업데이트 감지는 자동 브라우저 검증 범위에서 실행하지 못했다.
- 분리된 JS 파일은 SW의 네트워크 성공 응답 캐시에 들어가지만 `ASSETS_TO_CACHE` 선캐시 목록에는 포함되지 않았다. brief가 `CACHE_NAME` 증가만 요구해 범위를 넓히지 않았으며, 설치 직후 오프라인 진입 시나리오는 별도 확인이 필요하다.

## Fix round 1

### 수정 내용

- `static/sw.js`의 `ASSETS_TO_CACHE`에 분리 스크립트 5개를 로드 순서대로 추가하고 `CACHE_NAME`을 `2026.08.01.28`로 올렸다.
- `static/js/pwa.js`의 pull-to-refresh가 브리지 함수의 타입을 확인한 뒤 호출하도록 변경해, `initializeAuth` 지연 중 브리지가 아직 없더라도 오류 없이 정리 상태로 돌아가게 했다.
- `static/js/auth.js`의 DB 스코프 설명을 현재 전역 `db.js` 구조와 독립 로그아웃 트랜잭션 의도에 맞게 수정했다.
- `tests/test_frontend_guidelines.py`에 분리 파일 존재/로드 순서, SW 선캐시, 브리지 미준비 pull-to-refresh 동작 회귀 테스트를 추가했다.

### RED/GREEN 증거

- RED: `.venv/bin/python -m pytest tests/test_frontend_guidelines.py -q -k 'split_app_scripts or service_worker_precaches or pull_refresh_is_safe'` → 1 passed, 2 failed. SW 선캐시 누락과 브리지 TypeError를 각각 재현했다.
- GREEN: 같은 명령 → 3 passed.

### 최종 검증

- `node --check static/js/toast.js && node --check static/js/utils.js && node --check static/js/db.js && node --check static/js/auth.js && node --check static/js/pwa.js && node --check static/app.js` → 통과.
- `.venv/bin/python -m pytest tests/test_frontend_guidelines.py -q` → 23 passed.
- `.venv/bin/python -m pytest -q` → 135 passed, 174 warnings.
- `git diff --check` → 통과.

### 남은 우려사항

- 실제 OAuth 완료, 파일 업로드/생성, 실제 터치 장치의 pull-to-refresh와 백그라운드 복귀는 자동화 검증 범위 밖이다.
