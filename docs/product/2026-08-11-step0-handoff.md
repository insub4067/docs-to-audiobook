# Step 0 — 남은 작업 핸드오프

> 작성일: 2026-08-11
> 대상: 이 브랜치를 이어받는 로컬 에이전트
> 설계 원본: `2026-08-11-step0-curation-automation-design.md` (반드시 먼저 읽을 것)
> 브랜치: `claude/news-curation-pivot-u9ktj1`

이 문서는 "무엇이 끝났고, 다음에 무엇을 어떻게 하면 되는지"만 담는다. 설계 근거·트레이드오프·ADR은 설계 원본에 있으니 중복하지 않는다.

---

## 1. 지금까지 (이 브랜치에 병합됨)

| 커밋 | 내용 | 실행 경로 영향 |
|---|---|---|
| 피벗 검토 | `2026-08-11-news-pivot-review.md` | 문서 |
| Step 0 설계 | `2026-08-11-step0-curation-automation-design.md` | 문서 |
| 1단계 | `_normalize_items` 추출 + `SUPABASE_SETUP.md` 스키마 | **동작 변화 없음** (순수 리팩터) |
| 2단계 | `news_sources.py` (RSS 수집) + `feedparser` 의존성 | **없음** (아직 아무 데도 연결 안 됨) |
| 마이그레이션 | `news_curation_step0` 프로덕션 적용 | 스키마만. 새 컬럼은 nullable, 기본값이 기존 행을 보호 |
| 3단계 (1/2) | `summarizer.py` (Claude 선별·요약) + `anthropic` 의존성 | **없음** (아직 아무 데도 연결 안 됨) |
| 3단계 (2/2) | `_normalize_items` url/guid 통과 + `store_news_item`이 새 컬럼 저장 | **붙여넣기 경로 동작 그대로** (아래 참고) |

`git log --oneline origin/main..HEAD`로 확인. 백엔드 400건 통과, ruff 통과.

**중요: 여기까지도 사용자에게 보이는 동작이 하나도 바뀌지 않았다.** 관리자 붙여넣기
경로(`POST /api/admin/news`)가 그대로 살아 있고, 자동 수집·요약은 어디에서도
호출되지 않는다. 되돌리기가 안전한 마지막 지점이다 — 4단계부터는 프로덕션에서
실제로 도는 코드가 들어간다.

3단계 (2/2)가 붙여넣기 경로를 건드리지만 동작은 같다: 새 컬럼은 `None`으로
들어가고 `news_status`는 `'published'`가 기본이다. 기존 news 테스트 18건이
그대로 통과하는 것으로 확인했다.

---

## 2. 로컬 환경 준비 (맥북)

```bash
# 가상환경 (레포에 .venv가 없다 — 새로 만든다)
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
pip install pytest pytest-asyncio pytest-cov httpx ruff
```

### 알려진 함정

- **`pywebpush==2.3.0` → `http-ece` 빌드 실패 가능.** 원격 컨테이너에서 이 휠 빌드가 실패했다. 맥에서도 실패하면 `brew install` 없이도 대개 빌드 가능하지만, 막히면: `push_notifications.py`의 pywebpush import는 **함수 안 lazy import**라 테스트에는 필요 없다(브로드캐스트는 patch됨). 테스트만 돌릴 거면 pywebpush를 건너뛰어도 된다. 배포(fly.io Docker)에는 이미 들어 있으니 requirements는 그대로 둘 것.
- **`pytest.ini`에 `--cov` 옵션이 박혀 있다.** `pytest-cov`를 안 깔면 pytest가 인자 에러를 낸다. 깔거나 `-o addopts=""`로 우회.
- **테스트 실행**: `cd backend && python3 -m pytest -q` (레포 루트의 `pytest.ini`가 rootdir를 잡는다). 프론트: `cd frontend && npm ci && npm test`.

### DB 마이그레이션 — 적용 완료 ✅ (2026-08-11)

`SUPABASE_SETUP.md` §2.8.1의 SQL을 프로덕션에 적용했다(마이그레이션 이름 `news_curation_step0`). 적용 후 확인한 것:

- `service_role`의 news_sources SELECT/INSERT/UPDATE/DELETE 전부 `true` — 문서가 경고한 `42501` 사고 없음
- `anon`·`authenticated`는 SELECT `false` — 의도대로 차단
- `audiobooks`에 `news_status`/`news_url`/`news_guid` 3개 컬럼 + `audiobooks_news_guid_idx` unique index 생성
- **기존 붙여넣기 뉴스 10건이 그대로 남아 있고 전부 `news_status='published'`** — 기본값 덕에 향후 필터에서 사라지지 않는다
- `GET /api/news`가 10건을 그대로 반환(프로덕션 확인)

즉 이제 `news_url`/`news_guid`/`news_status`를 insert해도 깨지지 않는다.

---

## 3. 남은 작업

설계 원본 §10의 구현 순서 3~7단계. 각 단계는 독립 배포 가능하고, 앞 단계 없이 뒷 단계를 못 한다.

### 3단계 — `summarizer.py` + 저장 경로 확장 ✅ 완료 (2026-08-11)

커밋 두 개로 나눠 넣었다. 핸드오프 원안은 둘을 한 단계로 묶었는데, 저장 경로
확장은 마이그레이션 없이는 붙여넣기 경로를 죽이는 변경이라 분리했다.

**`summarizer.py`** — `claude-opus-5` + `messages.parse()` + Pydantic. effort는
`medium`. 400자 초과는 자르지 않고 한 번 재시도, 두 번째도 넘치면 그 항목만 버린다.
출처·링크 없는 항목 거부. 클라이언트는 호출 시점에 만든다(import 시점이면 키 없는
환경에서 모듈 자체를 못 읽는다). 테스트 8건.

> ⚠️ **`MAX_TOKENS = 16000`을 줄이지 말 것.** Claude Opus 5는 thinking이 기본으로
> 켜져 있고 thinking과 응답이 같은 한도를 나눠 쓴다. 5건 × 400자면 응답만 보고
> 3천 토큰이면 될 것 같지만, 그렇게 잡으면 답이 중간에 잘린다.

**저장 경로** — `_normalize_items(items, *, automated=False)`가 url/guid를
통과시키고, `store_news_item(..., news_status="published")`이 새 컬럼을 저장한다.
테스트 6건 추가, 기존 18건 그대로 통과.

**핸드오프가 남긴 결정 — 이렇게 정했다.** 설계 §3.2는 매체명·원문 링크가 없으면
거부하라고 하지만 붙여넣기 경로는 둘 다 보낸 적이 없다. **자동 경로(`automated=True`)에만
걸었다.** 자동 수집분은 사람이 본 적 없는 글이라 출처를 되짚을 수 있어야 하고,
붙여넣기는 관리자가 직접 확인하고 넣는 것이다.

> ⚠️ **여기서 한 번 틀렸으니 같은 실수를 반복하지 말 것.** 프로덕션 뉴스 10건이
> 매체명을 전부 채우고 있는 것을 보고 "필수"라고 판단해 양쪽 모두에 걸었다가
> 기존 테스트 13건이 깨졌다. 그건 관리자가 매번 넣어준 것이지 API가 요구한 게
> 아니다. **데이터가 우연히 채워진 것과 계약이 요구하는 것은 다르다** —
> 스키마·데이터가 아니라 테스트를 계약으로 읽을 것.

### 4단계 — `briefing.py` 트리거 ⬅ 다음 차례

**목표:** 수집→요약→기존 파이프라인을 잇는 HTTP 엔드포인트.

> **여기서 성격이 바뀐다.** 3단계까지는 만들어만 뒀고 아무 데도 안 붙었다.
> 4단계는 **프로덕션에서 실제로 도는 첫 코드**다. 되돌리기 단위를 작게 유지하려면
> 별도 PR로 가는 게 좋다.

**3단계에서 이미 끝나서 여기서 안 해도 되는 것:**

- `_normalize_items`의 url/guid 통과 — `automated=True`로 부르기만 하면 된다
- `store_news_item`의 새 컬럼 저장 — `news_status="review"`를 건네기만 하면 된다
- 마이그레이션 — 프로덕션에 적용 완료

**시작 전 확인:** fly.io secrets에 `ANTHROPIC_API_KEY`가 등록돼 있는지. 3단계에서
코드만 넣었고 키는 아직 안 넣었다 — 없으면 `summarize_category`가
`RuntimeError("ANTHROPIC_API_KEY가 설정되지 않았습니다.")`로 죽는다.

- 새 파일 `backend/routes/briefing.py`, `main.py`에 라우터 등록.
- `POST /api/admin/briefing/run` — `Authorization: Bearer BRIEFING_TRIGGER_SECRET` 검증(`state.py`에 헬퍼 추가). **즉시 202 반환 + `BackgroundTasks`로 처리** (`add_news`와 같은 방식, TTS 포함 수 분 걸림).
- 흐름: `collect_candidates()` → `summarize_category()` → `_normalize_items()` → `queue_jobs(supabase, "news", ...)` → `run_jobs()`. **queue_jobs 이후는 신규 코드 0줄** — 기존 content_jobs 파이프라인이 TTS·업로드·재시도를 한다.
- 완료 시 관리자에게 웹푸시(`push_notifications.py` 재사용, "오늘 뉴스 N건 검토 대기").
- **실패 처리는 기존 `_process_news_batch` 원칙 그대로**: 새 묶음이 하나라도 성공한 뒤에만 이전 뉴스 삭제 / 후보 0건이면 아무것도 안 함 / in-flight면 429.

**테스트** (`backend/tests/test_briefing.py`): 잘못된 토큰 401 / 처리 중이면 429 / 후보 0건이면 기존 뉴스 안 지움 / 자동 생성분은 `news_status='review'`로 저장.

**완료 기준:** GitHub Actions의 `workflow_dispatch`(6단계에서 만든 파일)로 수동 실행해서 end-to-end 검증. 또는 로컬에서 curl.

---

### 5단계 — 승인 게이트 + 관리자 UI

- `store_news_item`은 4단계에서 이미 `news_status='review'`로 저장. 여기서 **`GET /api/news`에 `.eq("news_status", "published")` 필터 추가**.
- `/admin`에 승인 탭: 서점의 '발행 관리' 구조(`library_status` review→published 전환)를 그대로 복제. `PATCH`로 `news_status`를 published로.
- 프론트를 고쳤으면 **`frontend/static/sw.js`의 `CACHE_NAME`을 올린다** (안 올리면 배포해도 기존 사용자에게 반영 안 됨).

**테스트**: `test_news.py`에 `news_status='review'`는 공개 목록에 안 나온다 추가. 프론트는 Vitest.

---

### 6단계 — cron 활성화

- 새 파일 `.github/workflows/daily-briefing.yml` (설계 §2에 전문):
  - `cron: "30 19 * * *"` (04:30 KST) + `workflow_dispatch`.
  - curl로 `POST /api/admin/briefing/run` (Bearer secret, `--max-time 60`).
- GitHub 레포 Secrets에 `BRIEFING_TRIGGER_SECRET` 등록, fly.io secrets에도 같은 값.
- **여기서 처음으로 자동으로 돈다.** 그 전(3~5단계)까지는 `workflow_dispatch` 수동 실행만.
- 주의: Actions cron은 피크에 10~60분 지연됨(정상). 06:00 목표에 04:30 발화로 여유.

---

### 7단계 — 출처·원문 링크 노출 (프론트, 저작권 필수)

- `frontend/components/News/*`: 목록 카드와 리더에 **매체명 + 원문 링크** 노출.
- 오디오 본문 끝의 "○○ 보도입니다"는 요약 텍스트에 포함되므로(3단계) 별도 처리 불필요.
- `sw.js` `CACHE_NAME` 올리기.

---

## 4. 지표 (병행)

`product_events`에 이벤트만 추가(대시보드는 나중): `briefing_generated` / `briefing_published` / `news_play_started` / `news_play_completed`. 설계 §9.

---

## 5. 범위 밖 (하지 말 것)

개인화 · 카테고리 확장(Step 1) · 프롬프트 캐싱 · 유료화 · 이름 변경 · 문서 기능 축소 · 기사 본문 크롤링. 설계 §11.

---

## 6. 작업 규칙 (이 레포)

- `CLAUDE.md`: UI/기획은 `.claude/apple-design-principles.md`·`toss-design-principles.md`, 코드는 `.claude/development-guidelines.md` 기준.
- 코드 변경엔 동작 검증 테스트를 함께. 통과하지만 아무것도 검증 안 하는 테스트 사례가 있었으니(`docs/troubleshooting/04-vacuous-delete-test.md`), 수정을 잠시 되돌려 실제로 실패하는지 확인할 것.
- 프론트 고치면 `sw.js` `CACHE_NAME` 올리기. `/`·`/admin`은 빌드 산출물(`static/dist/`)을 서빙하니 소스만 고치고 빌드 안 하면 반영 안 됨.
- Vitest는 2.x 고정(올리면 esbuild 충돌로 배포까지 깨짐).
