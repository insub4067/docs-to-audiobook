# 소스 정리 계획 (2026-08-09)

대상 브랜치: `claude/source-code-review-j9vr4l`
기준선: pytest 335개 / vitest 203개 전부 통과 (작업 시작 시점)

## 이 문서의 범위

서비스는 정상 동작 중이다. 기능을 바꾸는 작업이 아니라, **코드를 읽고 고치는
비용을 줄이는 작업**만 모았다. 기존 평가 문서(`project-evaluation-2026-08-05.md`,
`project-review-2026-08-07.md`)에서 이미 완료 표시된 항목은 제외했고, 그 이후에
남았거나 새로 생긴 것만 다룬다.

원칙은 `.claude/development-guidelines.md` §11을 따른다 — **정리와 기능 변경을
같은 커밋에 섞지 않는다.** 아래 각 항목은 독립 커밋으로 간다.

---

## Phase 1 — 동작·성능에 영향이 있는 것

### 1-1. 관리자 업로드 상한이 프론트/백엔드에서 다르다

| 위치 | 값 |
|---|---|
| `backend/state.py` `MAX_ADMIN_UPLOAD_BYTES` | 250MB |
| `frontend/Generation/Generation_Logic.vue` `getUploadLimitBytes()` | **50MB** |
| `frontend/Sheet/AddSourceSheet_View.vue` 라벨 | "최대 10MB" (비관리자) |

관리자가 50~250MB 문서를 올리면 서버에 닿기 전에 클라이언트가 거절한다.
스캔본 PDF 폴백이 정확히 이 크기대의 관리자 기능이라 실제로 막힌다.

더 근본적인 문제는 "업로드 상한"이라는 **하나의 지식이 세 곳에 하드코딩**된
것이다(§4 DRY). 값을 고치려면 세 곳을 찾아 고쳐야 하고, 실제로 어긋났다.

**처방:** 백엔드를 단일 출처로 삼는다. 이미 존재하는 `GET /api/config`에 상한을
실어 보내고, 프론트는 그 값을 쓴다. 라벨 문구도 같은 값에서 파생시킨다.

### 1-2. 대용량 합성 경로의 O(n²) 두 곳 — `backend/routes/tts.py`

```python
# advance_ready_prefix() — 청크가 끝날 때마다 오프셋을 처음부터 다시 합산
offset = sum(chunk_results[i]["duration"] for i in range(ready_count))

# publish_ready_chunks() — 청크가 끝날 때마다 문장 리스트를 통째로 새로 만듦
job["sentences"] = job.get("sentences", []) + [...]
```

`MAX_ADMIN_SYNTH_CHARS = 50_000_000`, 청크 800자 기준 **62,500 청크**다. 앞은
약 2×10⁹회 덧셈, 뒤는 약 2×10¹⁰회 원소 복사가 된다.

지금 다루는 크기(경전 ~4M자, 5,000청크)에서는 수 초라 눈에 띄지 않는다. 다만
상한 근처에서는 합성보다 부기(簿記)가 더 오래 걸리는 구간이 생긴다. 두 곳 다
**한 줄 수정**이라 지금 갚는 비용이 거의 0이다.

**처방:** 누적 오프셋을 `nonlocal`로 들고 다니고, 리스트는 `.extend()`로 붙인다.

### 1-3. `_rate_buckets`가 정리되지 않는다 — `backend/state.py`

`(엔드포인트, IP)` 키로 쌓이기만 하고 `cleanup.py`의 정리 대상에 없다.
`text_storage`·`jobs`·공유 파일·고아 오디오는 모두 정리하는데 이것만 빠졌다.
Fly의 suspend/재시작으로 리셋돼 왔을 뿐, 구조적으로는 무한히 자란다.

**처방:** 정리 루프에 "윈도가 지난 버킷 제거"를 추가한다.

### 1-4. Supabase 클라이언트를 호출마다 새로 만든다 — `backend/auth.py`

`create_client()`가 캐싱 없이 불린다. `_supabase_or_503()` 호출 지점이 **49곳**
이고(`library.py` 9, `audiobooks.py` 7), 요청 하나가 여러 번 부르는 경로도 있다.
매번 새 httpx 세션이 생긴다.

**처방:** 성공한 클라이언트만 `use_service_role` 단위로 재사용한다.
실패(`None`)는 캐시하지 않는다 — 부팅 시 일시적 실패가 영구 장애가 되면 안 된다.

---

## Phase 2 — 죽은 코드

### 2-1. `backend/models.py` 전체(92줄)

`UserRegister`/`UserLogin`/`TokenResponse`/`UserDB`… 전부 이메일+비밀번호 가입용
스키마인데, 실제 인증은 소셜 로그인(`auth_social.py`)뿐이다. 참조하는 곳은
`tests/test_models.py` 하나로, **죽은 코드를 테스트가 살려두고 있는** 형태다.
지금도 Pydantic V2 deprecation 경고를 3건 낸다.

`requirements.txt`의 `email-validator`도 이 파일의 `EmailStr` 때문에 들어간
것이므로 함께 정리한다.

### 2-2. README 프론트매터의 포트

`README.md`가 `app_port: 8080`인데 `Dockerfile`/`fly.toml`은 7860이다.
HuggingFace Spaces 시절 잔재다.

---

## Phase 3 — 중복 (Rule of Three 충족)

### 3-1. Storage 2단 업로드 + 보상 삭제가 정확히 세 곳

`routes/news.py`, `routes/library.py`, `routes/tts.py`에서 "mp3 업로드 → 문장
JSON 업로드 → 실패하면 mp3 되돌리기"가 그대로 반복된다. §4의 Rule of Three
("세 번째 사례가 나올 때 뽑는다")에 이제 도달했다.

**처방:** `state.py`에 오디오+문장 한 쌍을 올리는 함수 하나로 모은다. 세 곳의
공통점은 "이 두 객체는 항상 함께 존재해야 한다"는 **불변식**이므로, 그 불변식을
지키는 책임을 한 곳에 둔다.

### 3-2. 관리자 SPA의 `Bearer` 헤더 수동 조립 8회

메인 앱은 `authLogic.authHeaders()`로 이미 한 곳에 모여 있는데,
`Admin/Admin_Logic.vue`만 `` `Bearer ${localStorage.getItem("authToken")}` ``을
8번 반복한다. 관리자 SPA는 `Auth_Logic`을 쓰지 않아 생긴 갈래다.

---

## Phase 4 — 일관성 (§12)

| 항목 | 현재 | 처방 |
|---|---|---|
| 로깅 | `print` 26회 / `logger` 26회가 파일 단위로 갈림. `tts.py`는 한 파일에서 둘 다 씀 | `logging`으로 통일 |
| `state.py` 네이밍 | `_supabase_or_503` 등 6개가 `_` 접두인데 실제로는 다른 모듈이 import하는 공개 API | 접두사 제거 |
| datetime | `auth.py`는 naive(`utcnow()`), 나머지는 aware(`now(timezone.utc)`) | aware로 통일 |
| 시작 훅 | `@app.on_event("startup")` (FastAPI deprecated) | `lifespan`으로 전환 |
| 삼킨 예외 | `cleanup.py`의 `except Exception: pass` — 백엔드 유일 | 경고 로그 |

---

## 이번에 하지 않는 것 (근거와 함께 남긴다)

**예외 원문이 클라이언트로 나가는 31곳** (`detail=f"...: {e}"`)
Supabase 예외에 테이블·컬럼명이 실려 나간다. 다만 31곳을 한 번에 바꾸면 사용자에게
보이는 오류 문구가 전부 달라지고, 그건 정리가 아니라 **UX 결정**이다. 어떤 정보를
남기고 무엇을 감출지 정한 뒤 별도 작업으로 간다.

**큰 파일 분할** — `Reader_Logic.vue` 835줄, `tts.py` 787, `Generation_Logic.vue` 721,
`AudioList_Logic.vue` 573
`tts.py`는 순환 참조를 피하려 뭉쳐 뒀다는 근거가 파일 상단에 있어 그대로 둔다.
나머지는 분할 근거가 뚜렷하지만(특히 `Reader_Logic`은 재생·하이라이트·장 이동·
북마크·시트·공유가 한 클로저에 있다), 동작을 바꾸지 않는 대규모 이동이라 이번
정리와 섞으면 리뷰가 불가능해진다. §11에 따라 **그 파일을 다음에 기능으로 건드릴 때**
같이 한다.

**`Reader_Logic`의 시트 보일러플레이트 12개** (`openX`/`closeX`/`closeXIfOpen` × 4)
위 분할과 같은 커밋에서 처리하는 게 맞다.

**`09-misc.css` 835줄의 이름** — catch-all 이름이지만, 바꾸려면 `app.html`의 link
순서와 `test_frontend_guidelines.py`의 `STYLE_SHEET_ORDER`가 함께 움직여야 한다.
내용을 실제로 나눌 때 같이 한다.

**CI가 테스트를 기다리지 않고 배포하는 것** — `ci-cd.yaml`의 deploy 잡에 `needs: test`가
없다. 워크플로 주석에 **의도라고 적혀 있으므로** 버그가 아니다. 바꾸려면 배포 정책
자체를 정해야 하는 문제라 여기서 건드리지 않는다.

---

## 결과 (2026-08-09 완료)

| Phase | 상태 | 커밋 |
|---|---|---|
| 1-1 업로드 상한 단일 출처 | 완료 | `ec639e2` |
| 1-2 O(n²) 두 곳 / 1-3 버킷 정리 / 1-4 클라이언트 재사용 | 완료 | `fc961f5` |
| 2-1 models.py 제거 / 2-2 README 포트 | 완료 | `3bd3f5b` |
| 3-1 Storage 업로드 통합 / 3-2 관리자 인증 헤더 | 완료 | `3ff0759` |
| 4 로깅 일원화 + lifespan | 완료 | `0f920d6` |
| 4 state.py 네이밍 | 완료 | `38bc206` |

테스트: 335 → **344** (pytest), 203 → **208** (vitest). 백엔드 커버리지 89% → 90%.

### 작업 중에 발견한 것 (계획에 없던 것)

**로깅 설정이 어디에도 없었다.** print를 logger로 옮기려다 확인했는데,
uvicorn은 자기 로거만 설정하고 루트는 건드리지 않는다. 그래서 애플리케이션
로거는 `logging.lastResort`(WARNING 이상만 출력)로 떨어진다.

- 그대로 옮겼다면 print로 보이던 메시지들이 **조용히 사라질 뻔했다.**
- 기존 `push_notifications.logger.info`도 같은 이유로 **한 번도 출력된 적이 없다.**

`main.configure_logging()`으로 루트를 INFO에 맞추고, 실제로 부팅해 INFO 한 줄이
stderr에 나오는 것을 확인했다.

**보상 삭제가 한 경로에서만 검증되고 있었다.** Storage 업로드 중복 세 곳 중
tts.py 경로에만 테스트가 있었다(`test_background_jobs`). 나머지 둘은 같은
코드인데 검증되지 않은 상태였다 — 합치면서 불변식을 새 자리에서 직접 검증한다.

**청크 알림의 오프셋이 검증되지 않고 있었다.** `chunk_ready_callback`이
넘겨주는 문장 시각(클라이언트가 합성 중 하이라이트에 쓰는 값)을 아무 테스트도
보고 있지 않았고, 인덱스만 검증하고 있었다. O(n²)를 고치기 전에 먼저 채웠다.

---

## 검증 방법

- 각 Phase마다 `pytest` + `vitest`를 돌려 335/203 기준선이 유지되는지 본다.
- 동작이 바뀌는 항목(1-1 ~ 1-4, 3-1)에는 회귀 테스트를 함께 넣는다.
- README 경고를 따라, 새로 넣은 테스트는 **수정을 잠시 되돌려 실제로 실패하는지**
  확인한다(`docs/troubleshooting/04-vacuous-delete-test.md`의 재발 방지).
- 프론트 변경이 있으므로 `frontend/static/sw.js`의 `CACHE_NAME`을 올린다.
