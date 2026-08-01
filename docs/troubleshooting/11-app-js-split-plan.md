# `static/app.js` 2차 분리 작업 기록 (완료)

## 최종 상태

- 저결합 모듈: `generation-status.js`, `voices.js`, `web-speech.js`, `reader-controls.js`
- 생성 흐름: `generation.js`
- 보관함·클라우드·액션시트: `library.js`
- 로컬/공유 리더·목차·자동 스크롤·공유 링크: `reader.js`
- `app.js`: 인증 이후 공용 상태, 공용 모달/스와이프 도우미, 컨트롤러 조립과 초기화, DB/PWA 부트스트랩만 담당

클래식 스크립트 로딩은 유지한다. 각 모듈은 `window.TextAudio`에 팩터리를 등록하고, `app.js`가 만든 `appContext`의 `elements`, `state`, `services`를 통해 필요한 의존성을 받는다.

## 조립 순서

1. 인증 초기화와 공용 DOM·상태를 준비한다.
2. 음성·생성 상태 서비스를 만든다.
3. `reader`를 등록한다.
4. `library`, `generation`을 등록한다.
5. 모든 서비스 등록 뒤 `voice → reader → library → generation` 순서로 `initialize()`한다.
6. IndexedDB 초기화 후 음성 목록과 보관함을 로드하고, 공유 링크·PWA·백그라운드 알림을 시작한다.

`reader`와 `library`의 순환은 mutable `services` 객체로 끊는다. 보관함 행은 `reader.open(audio)`를 호출하고, 리더는 `library.savePlaybackState()`와 `library.render()`를 호출한다. 필수 `library` 서비스가 없으면 리더 초기화와 저장 시점에 즉시 오류가 난다.

## 유지한 동작

- 로컬/공유 리더의 렌더링과 재생 흐름은 별도로 유지했다. 두 흐름의 중복은 이번 분리에서 제거하지 않았다.
- 공통 Escape는 로그인 프롬프트, 보관함 액션시트, 리더 목차, 생성 모달 순서로 닫는다.
- `reader.js`는 `reader-controls.js`, `web-speech.js` 뒤에, `app.js` 앞에 로드된다.
- 새 정적 파일은 Service Worker 프리캐시에 포함되며 캐시 버전은 `2026.08.02.6`이다.

## 검증

- `node --check static/app.js static/js/reader.js static/js/library.js static/sw.js`
- `.venv/bin/python -m pytest tests/test_frontend_guidelines.py -q`
- `.venv/bin/python -m pytest -q`

프런트 테스트는 `reader.js`의 공개 계약과 로컬 오디오북 진입 뒤 현재 문장 자동 스크롤을 실행으로 검증한다.
