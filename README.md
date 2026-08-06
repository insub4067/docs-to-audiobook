---
title: Docs To Audiobook
emoji: 🎧
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 8080
pinned: false
---

# TextAudio (docs-to-audiobook)

문서를 한국어 오디오북으로 바꿔 모바일에서 듣는 PWA. 개인이 올린 문서를 변환해 듣는 것이 핵심이고, 여기에 관리자가 큐레이션하는 **경제 뉴스**와 **고전 서점**이 붙어 있다.

**프로덕션**: https://docs-to-audiobook.fly.dev

> 이 문서는 사람과 AI 에이전트가 프로젝트를 빠르게 파악하도록 **현재 구현된 것만** 적는다. 계획·구상은 `docs/product/retention-roadmap.md`에 있다.

---

## 30초 요약

| | |
|---|---|
| **무엇** | 문서(PDF/DOCX/HWP/TXT/MD)·웹링크·유튜브·사진을 한국어 TTS 오디오북으로 변환해 듣는 PWA |
| **누구** | 모바일에서 개인 문서를 반복 청취하는 개인 학습·독서 사용자 |
| **백엔드** | FastAPI (Python 3.11) + Edge-TTS / Google Cloud TTS |
| **프론트** | Vue 3 SPA (Composition API) + Pinia + Vite, 별도 관리자 SPA |
| **저장** | Supabase(PostgreSQL + Storage) / 기기 로컬은 IndexedDB |
| **배포** | Fly.io (Docker), GitHub Actions CI/CD |
| **테스트** | 백엔드 pytest 247개 + 프론트 Vitest 43개 |

---

## 화면 구조

하단 4탭으로 나뉜다.

| 탭 | 하는 일 |
|---|---|
| **홈** | 문서 업로드/변환, 경제 뉴스 요약 카드, 최근 추가·즐겨찾기 목록 |
| **서재** | 내가 만든 오디오북 관리 — 폴더, 이름 변경, 즐겨찾기, 공유, 삭제 |
| **서점** | 관리자가 등록한 고전(도덕경·논어·성경 등) 탐색 및 내 서재에 저장 |
| **프로필** | 계정, 읽기 설정(테마·글꼴·크기·줄간격·속도·반복·타이머), 로그아웃 |

읽기 화면(리더)은 탭과 별개로 전체화면으로 열리고, 닫아도 **미니 플레이어**로 재생이 이어진다.

---

## 기능

### 문서 → 오디오북 변환

- **파일 업로드**: `.pdf` `.docx` `.hwp` `.txt` `.md` (일반 사용자 10MB, 관리자 250MB)
- **웹 링크**: 기사 URL을 넣으면 본문만 추출 (trafilatura)
- **유튜브**: 자막을 받아 변환
- **텍스트 붙여넣기**: 본문을 직접 입력
- **사진 스캔(OCR)**: 사진 속 글자를 Google Vision으로 인식
- **구글 드라이브**: 드라이브에서 문서를 직접 가져오기
- **스캔본 PDF 폴백**: 텍스트 레이어가 없는 PDF는 페이지를 이미지로 렌더링해 OCR (관리자)
- 여러 파일 동시 업로드 → 순차 처리

### 음성 합성

- 한국어 음성 2종: **현수**(자연스러운 남성), **선희**(차분한 여성)
- 음성마다 합성 엔진이 고정돼 있다(`voice_catalog.py`). 어댑터 구조라 Edge-TTS ↔ Google Cloud TTS 교체가 가능하다.
- 문장 단위 타임스탬프를 함께 생성해 리더의 문장 하이라이트·탭 이동에 쓴다.
- 청크 단위 재시도로 Edge-TTS의 간헐적 네트워크 오류를 넘긴다.
- **대용량 백그라운드 작업**: 큰 문서는 서버가 브라우저와 무관하게 처리하고, 완료되면 웹 푸시로 알린다.

### 리더 (읽기 화면)

- 문장 단위 하이라이트 + 자동 스크롤, 문장을 탭하면 그 지점부터 재생
- 마크다운 `#` 제목으로 **목차** 자동 생성, 표 렌더링
- ±10초 이동, 재생 속도(0.75x~2.0x), 반복 모드, 취침 타이머
- 반복 모드는 **재생목록 단위**로 동작한다 — 뉴스 연속 재생 중이면 목록을 순환하고, 목록이 없으면 그 오디오북을 반복한다
- 오디오 재생 실패 시 브라우저 내장 Web Speech API로 폴백
- 읽기 테마 4종(라이트/다크/웜/그레이), 글꼴·글자 크기·줄 간격 조절

### 서재 · 동기화

- IndexedDB에 오디오를 저장해 **오프라인 재생** 지원
- 로그인하면 Supabase Storage와 자동 동기화 (기기 간 이어 듣기)
- 폴더 만들기/이동(드래그앤드롭 포함), 제목 수정, 즐겨찾기, 삭제
- **공유 링크**: 오디오북을 링크로 공유(24시간), 받은 사람은 로그인 없이 청취 후 자기 서재에 저장 가능
- 기본 제공 오디오북(『데미안』)이 처음부터 들어 있어 가입 전에도 바로 들어볼 수 있다. 로그인 사용자는 이걸 지울 수 있다.

### 경제 뉴스 (관리자 큐레이션)

- 관리자가 JSON으로 뉴스를 넣으면 서버가 TTS로 변환해 공개 목록에 올린다
- 로그인 없이 누구나 볼 수 있고, **3일 이내 최신 10건**만 노출한다
- "전체 듣기"로 연속 재생, 등록 시 구독자에게 웹 푸시 발송
- 새 뉴스를 등록하면 공개 목록에서 밀려난 오래된 뉴스는 DB·Storage에서 자동 정리된다

### 서점 / 라이브러리 (관리자 큐레이션)

- 고전 작품을 관리자가 등록한다 (도덕경, 논어, 금강경, 성경, 코란, 법구경 등)
- **발행 게이트**: 등록 시 기본값이 `review`(비공개)이고, 관리자가 명시적으로 `published`로 바꿔야 공개된다 — 판본 저작권 확인 전에는 노출하지 않기 위해서다
- 사용자는 작품을 자기 서재에 저장할 수 있다

### 계정 · 알림

- Google 소셜 로그인 (`auth_social.py`는 제공자 추가가 가능한 구조)
- 비로그인 사용자도 **1회 익명 체험** 가능
- 로그아웃 시 기기에 저장된 오디오북을 삭제하고, 그 전에 클라우드로 백업한다
- 웹 푸시 알림(대용량 변환 완료, 새 뉴스 도착)

### 관리자 화면 (`/admin`)

허용된 이메일(`ADMIN_EMAILS`)만 접근할 수 있는 **별도 SPA**다. 3탭 구조.

- **대시보드**: 사용자 수, 주간 활성 사용자, 생성 성공률, 재생 시작, 1주 재방문율 (개인 콘텐츠는 집계하지 않음)
- **콘텐츠 등록**: 경제 뉴스 / 라이브러리 작품을 JSON으로 등록 (붙여넣기 즉시 형식 검증 + 미리보기)
- **발행 관리**: 등록된 작품의 공개/비공개 전환

### PWA

- 홈 화면 설치, 오프라인 동작, 서비스워커 캐싱
- 당겨서 새로고침, 배포 감지 후 자동 리로드
- iOS 대응: safe-area, 바텀시트, 스와이프로 닫기

---

## 아키텍처

```
frontend/                Vue 3 SPA (메인) + 관리자 SPA, 두 개의 Vite 진입점
  app.html   → main.ts        → Home_View.vue     (사용자 앱, "/"가 서빙)
  admin.html → main-admin.ts  → Admin_View.vue    (관리자, "/admin"이 서빙)
  static/                     빌드 산출물(dist/)과 style.css·admin.css·sw.js
backend/                 FastAPI
  main.py                     앱 조립 + CORS + 정적 마운트
  routes/                     도메인별 라우트 (아래 표)
  tts_providers/              TTS 공급자 어댑터 (edge_tts / google)
  text_processing.py          문서 파싱·텍스트 정제·청킹
  state.py                    공용 설정·인증 헬퍼·업로드 상한
```

### 프론트엔드 컨벤션

화면·기능 단위로 **View / State / Logic** 3분할한다.

- `*_View.vue` — 마크업과 표현
- `*_State.vue` — 반응형 상태(ref)만
- `*_Logic.vue` — 동작·부수효과

상태는 대부분 **모듈 싱글턴**이지만, `ReaderControlsState` `ThemeState` `AdminState`는 **호출할 때마다 새로 만드는 팩토리**다. 이 셋은 최상위 컴포넌트에서 한 번만 만들어 props로 내려보낸다 — 다른 곳에서 `use*State()`를 또 부르면 연결이 끊긴 복사본이 생긴다.

상세 지침은 `.claude/development-guidelines.md`, UI 원칙은 `.claude/apple-design-principles.md` · `.claude/toss-design-principles.md`에 있다.

### 주요 API

| 그룹 | 엔드포인트 |
|---|---|
| 변환 | `POST /api/upload` `/api/synthesize` `/api/paste-text` `/api/extract-url` `/api/extract-youtube` `/api/scan-text` `/api/scan-pdf` `/api/import-drive-file` |
| 오디오북 | `GET·POST /api/audiobooks` `PATCH·DELETE /api/audiobooks/{id}` `GET·PUT /api/audiobooks/{id}/playback` |
| 폴더 | `GET·POST /api/folders` `PATCH·DELETE /api/folders/{id}` |
| 뉴스 | `GET /api/news` · `POST /api/admin/news` |
| 서점 | `GET /api/library` `/api/library/saves` `/api/library/{id}` · `POST·DELETE /api/library/{id}/save` · `POST·GET /api/admin/library` `PATCH /api/admin/library/{id}` |
| 공유 | `POST /api/share` · `GET /api/share/{id}` `/api/share/{id}/audio` |
| 계정·기타 | `POST /api/auth/social/{provider}` `GET /api/auth/me` `/api/voices` `/api/default-book` `/api/admin/metrics` `POST /api/events` `/api/push/subscriptions` |

### 데이터베이스 (Supabase)

`users` `audiobooks` `folders` `playback_history` `product_events` `push_subscriptions` `library_saves` `background_synthesis_jobs`

뉴스와 서점 작품은 별도 테이블 없이 `audiobooks`에 `is_news` / `is_library` 플래그로 구분한다.

> ⚠️ 새 테이블을 만들 때 `GRANT ... TO service_role`을 빠뜨리면 앱이 `42501 permission denied`로 500을 낸다. 실제로 `library_saves`가 이 문제로 기능 전체가 죽어 있었다. 절차는 `docs/SUPABASE_SETUP.md`에 있다.

---

## 개발

```bash
# 백엔드 (backend/.env 필요 — docs/SUPABASE_SETUP.md 참고)
.venv/bin/uvicorn main:app --app-dir backend --reload --port 8000

# 프론트엔드 빌드 (두 진입점을 각각 빌드해야 한다)
cd frontend
npm ci
npm run build       # 관리자 SPA
npm run build:app   # 사용자 SPA

# 테스트
python3 -m pytest -q     # 백엔드 247개
cd frontend && npm test  # 프론트 43개 (Vitest)
```

### 작업 시 주의

- **프론트를 고쳤으면 `frontend/static/sw.js`의 `CACHE_NAME`을 올린다.** 안 올리면 배포해도 기존 사용자에게 반영되지 않는다.
- `/` 와 `/admin`은 **빌드 산출물**(`static/dist/`)을 서빙한다. 소스만 고치고 빌드를 안 하면 반영되지 않는다.
- Vitest는 Vite 5와 esbuild를 공유하는 **2.x 계열로 고정**돼 있다. 올리면 esbuild가 둘로 갈려 `npm ci`가 깨지고 배포까지 막힌다.
- 코드 변경에는 동작을 검증하는 테스트를 함께 추가한다. 통과하는 테스트가 실제로 무엇도 검증하지 않는 사례가 있었으니(`docs/troubleshooting/04-vacuous-delete-test.md`), 수정을 잠시 되돌려 테스트가 실제로 실패하는지 확인하는 것을 권한다.

---

## 문서

| 문서 | 내용 |
|---|---|
| `docs/product/retention-roadmap.md` | 제품 방향·성공 지표·우선순위 |
| `docs/SUPABASE_SETUP.md` | DB 스키마, RLS, GRANT 절차 |
| `docs/troubleshooting/` | 실제로 겪은 문제와 원인 (읽을 가치가 높다) |
| `docs/large-admin-background-jobs.md` | 대용량 백그라운드 변환 설계 |
| `docs/project-evaluation-2026-08-05.md` | 코드베이스 종합 평가와 기술부채 |
| `.claude/development-guidelines.md` | 코드 작성 규칙 |
