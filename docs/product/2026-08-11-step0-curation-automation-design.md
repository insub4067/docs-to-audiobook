# Step 0 — 큐레이션 자동화 설계

> 작성일: 2026-08-11
> 선행 문서: `2026-08-11-news-pivot-review.md`
> 범위: 관리자 수동 붙여넣기 → 자동 수집·요약·합성. **개인화는 이 단계에 없다.**

## 목표 한 문장

> 인섭님이 매일 손으로 하는 큐레이션을 서버가 대신하고, 그 결과를 인섭님이 아침에 한 번 승인한다.

성공 조건은 "개인화된 브리핑"이 아니라 **"내일 아침에도 새 뉴스가 자동으로 준비돼 있다"** 하나다.

---

## 1. 전체 흐름

```
GitHub Actions cron (19:30 UTC = 04:30 KST)
   │  POST /api/admin/briefing/run   (Bearer BRIEFING_TRIGGER_SECRET)
   ▼
routes/briefing.py
   1. collect()     news_sources.py  — 화이트리스트 RSS에서 후보 수집
   2. summarize()   summarizer.py    — Claude가 선별 + 요약 (카테고리당 1회)
   3. queue_jobs(supabase, "news", ...)  ─┐
   4. run_jobs()  → store_news_item()     │  기존 코드 그대로
                  → synthesize_into_storage()  (TTS)
                  → audiobooks(is_news=true, news_status='review')  ─┘
   5. 관리자에게 웹푸시 "오늘 뉴스 N건 검토 대기"
   ▼
관리자가 /admin에서 승인 → news_status='published' → 공개 목록에 노출
```

**3~4단계는 신규 코드가 0줄이다.** `content_jobs` 파이프라인이 이미 "원문 저장 → TTS → Storage 업로드 → audiobooks insert → 실패 시 재시도"를 전부 한다. 앞단(1~2)만 붙이면 된다.

---

## 2. 스케줄러 — 인프로세스 루프가 아니라 GitHub Actions

`cleanup.py`에 이미 `while True` 백그라운드 루프가 있으니 그 패턴을 따르는 게 일관성 면에서는 자연스럽다. 그럼에도 외부 cron을 쓴다.

| | 인프로세스 루프 | GitHub Actions cron |
|---|---|---|
| 배포 시 | 스케줄이 리셋된다 (fly.io는 배포마다 프로세스 재시작) | 영향 없음 |
| 관측 | 로그를 뒤져야 한다 | 실행 이력 · 실패 알림 · 재실행 버튼 |
| 수동 실행 | 없음 | `workflow_dispatch` |
| 중복 방지 | 재시작 직후 두 번 도는 경우 방어 필요 | 서버 쪽 in-flight 체크로 충분 |

`cleanup.py`의 루프는 임시파일 정리라 한 번 걸러도 무해하다. 일일 브리핑은 조용히 안 돌면 제품이 죽는다 — **신뢰도 요구가 다르므로 다른 메커니즘을 쓴다.** 이 판단을 ADR로 남긴다(`.claude/development-guidelines.md` §13.2).

주의할 점 두 가지:

- **Actions cron은 정시에 안 뜬다.** 피크 시간대에 10~60분 지연되는 것이 정상이다. 그래서 06:00 목표에 04:30 발화로 90분 여유를 둔다.
- **fly.toml이 `auto_stop_machines = 'suspend'`다.** `auto_start_machines = true`이므로 인바운드 요청이 머신을 깨운다. 첫 요청이 콜드 스타트를 먹지만 배치 작업이라 상관없다.

```yaml
# .github/workflows/daily-briefing.yml
name: 일일 브리핑 생성
on:
  schedule: [{ cron: "30 19 * * *" }]   # 04:30 KST
  workflow_dispatch:
jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - name: 브리핑 생성 요청
        run: |
          curl -sS --fail-with-body -X POST \
            -H "Authorization: Bearer ${{ secrets.BRIEFING_TRIGGER_SECRET }}" \
            --max-time 60 \
            https://docs-to-audiobook.fly.dev/api/admin/briefing/run
```

엔드포인트는 **즉시 202를 돌려주고 `BackgroundTasks`로 처리한다** (`add_news`와 같은 방식). TTS까지 포함하면 수 분이 걸리는데 curl을 붙잡고 있을 이유가 없다.

---

## 3. 저작권 안전 설계 — 여기가 이 단계의 핵심 제약

피벗 검토 문서에서 확인한 대로, 2026년 한국에서 "뉴스 자동 수집 + AI 요약 + 낭독"은 정부가 침해로 해석한 행위와 겹친다. **나중에 얹을 수 없는 제약이므로 Step 0에 박아 넣는다.**

### 3.1 `extract_url.py`를 쓰지 않는다

기술적으로는 지금 당장 가능하다 — trafilatura로 기사 본문을 뽑는 코드가 이미 있고 SSRF 방어까지 돼 있다. **그래도 쓰지 않는다.**

입력은 RSS 피드가 제공하는 `<title>` + `<description>`(또는 `<summary>`)만 쓴다. 이건 언론사가 배포 목적으로 스스로 공개한 필드다. 본문 전문을 긁어 요약하는 것과는 법적 위치가 다르다.

> 트레이드오프: 피드 요약만으로는 요약 품질이 떨어진다. 특히 description이 한 줄짜리인 매체가 있다. 이건 **감수한다.** 품질을 원문 크롤링으로 올리는 선택지는 Step 0의 목적(안전하게 자동화)과 정면으로 충돌한다.

### 3.2 코드로 강제하는 규칙

```python
SUMMARY_MAX_CHARS = 400   # 한국어 2~3문장, TTS 약 45초
```

- 요약이 상한을 넘으면 **자르지 않고 거부하고 한 번 재시도한다.** 자르면 문장이 깨져서 TTS가 이상해진다.
- `news_url`(원문 링크)이 없으면 저장을 거부한다.
- `news_source`(매체명)가 없으면 저장을 거부한다.
- 소스는 `news_sources` 테이블에 관리자가 등록한 것만. 임의 URL 수집 경로를 만들지 않는다.

### 3.3 화면·오디오 표기

- 목록 카드와 리더 화면에 **매체명 + 원문 링크**를 반드시 노출한다.
- 오디오 본문 끝에 `"{매체명} 보도입니다."` 한 문장을 붙인다. (TTS 텍스트에 포함 — 별도 처리 불필요)

### 3.4 승인 게이트 — 서점 패턴 재사용

라이브러리가 판본 저작권 때문에 `library_status`(`review`/`published`) 게이트를 이미 갖고 있다. 뉴스에 같은 것을 만든다.

자동 생성분은 `news_status='review'`로 들어가고, 관리자가 승인해야 공개된다. **완전 무인화는 Step 1 이후**로 미룬다 — 요약 품질이 검증되기 전에 자동 공개하면 이상한 요약이 그대로 나간다.

승인이 병목이 되지 않게: 생성 완료 시 **관리자에게 웹푸시**를 보낸다(`push_notifications.py` 재사용). 폰에서 30초면 끝난다.

---

## 4. LLM 설계

### 4.1 모델과 파라미터

| 항목 | 값 | 이유 |
|---|---|---|
| 모델 | `claude-opus-5` | 기본값. 아래 비용 계산대로 비용이 제약이 아니다 |
| effort | `medium`부터 시작 | Opus 5는 low/medium이 유난히 강하다. 요약·선별은 난이도가 높지 않다. 품질 보고 조정 |
| thinking | 기본값(adaptive) | Opus 5는 생략하면 adaptive다. 중요도 판단에 도움이 된다 |
| 구조화 출력 | `client.messages.parse()` + Pydantic | JSON 파싱 실패 경로가 사라진다 |
| Batch API | **쓰지 않는다** | 아래 참고 |

**Batch API를 쓰지 않는 이유:** 50% 할인이지만 "대부분 1시간 내, 최대 24시간"이다. 아래 계산대로 절감액이 월 $1.6 수준인데 최대 24시간 지연 리스크를 지는 건 맞지 않는다. 일일 브리핑에서 지연은 곧 제품 실패다.

**프롬프트 캐싱도 Step 0에서는 넣지 않는다.** 카테고리가 '경제' 하나뿐이라 하루 1회 호출이고, 캐시 TTL(5분/1시간)보다 호출 간격이 훨씬 길어서 이득이 0이다. 카테고리가 2개 이상 되는 Step 1에서 — 같은 실행 안에서 시스템 프롬프트를 공유하게 될 때 — 넣는다. (`development-guidelines.md` §14.5: 요청되지 않은 것을 만들지 않는다)

### 4.2 호출 구조 — 카테고리당 1회

선별과 요약을 **한 호출로 합친다.** 중복 사건 제거와 중요도 비교에는 후보 전체의 맥락이 필요하고, 호출이 1회면 실패 지점도 1개다.

카테고리별로는 **나눈다.** 이유는 실패 격리다 — 경제가 실패해도 AI 뉴스는 나와야 한다. Step 0에서는 카테고리가 하나라 효과가 없지만, 구조를 이렇게 잡아두면 Step 1에서 자연히 확장된다.

```python
# backend/summarizer.py
from pydantic import BaseModel, Field

class NewsItem(BaseModel):
    title: str = Field(description="기사 제목. 원문 제목을 그대로 쓰지 말고 내용을 나타내게 다시 쓴다.")
    content: str = Field(description="2~3문장 요약. 400자 이내. 원문 문장을 그대로 옮기지 않는다.")
    source: str = Field(description="매체명")
    url: str = Field(description="원문 링크")
    guid: str = Field(description="입력으로 준 후보의 guid를 그대로 돌려준다")

class Briefing(BaseModel):
    items: list[NewsItem]

async def summarize_category(category: str, candidates: list[dict], limit: int) -> list[NewsItem]:
    ...
```

시스템 프롬프트가 담아야 할 것:

- 역할: 오디오로 들을 뉴스 브리핑을 만든다. 눈으로 읽는 게 아니라 **귀로 듣는다** — 숫자와 고유명사를 읽기 쉽게 풀어쓴다.
- 선별 기준: 같은 사건을 다룬 후보는 하나만 남긴다. 중요도 순으로 최대 N건.
- **저작권**: 원문 문장을 그대로 옮기지 않는다. 사실만 요약한다. 원문을 직접 인용하지 않는다.
- 길이: 400자 이내. 넘기면 안 된다.
- 출처: 입력에 있는 매체명과 링크를 그대로 돌려준다. 지어내지 않는다.

### 4.3 비용

카테고리 1개, 후보 30건 기준:

| | 토큰 | 단가 | 일 비용 |
|---|---|---|---|
| 입력 (시스템 프롬프트 + 후보 30건) | ~9,000 | $5/MTok | $0.045 |
| 출력 (10건 × 250토큰) | ~2,500 | $25/MTok | $0.063 |
| **합계** | | | **$0.11/일 ≈ 월 $3.3** |

TTS는 edge-tts라 무료다. 카테고리를 6개로 늘려도 월 $20 수준이다.

> **결론: 비용은 이 설계에서 제약이 아니다.** 비용을 아끼려고 모델을 낮추거나 Batch API를 쓰는 최적화는 하지 않는다. 아끼는 금액이 감수하는 리스크보다 작다.

---

## 5. 데이터 모델

```sql
-- 소스 화이트리스트. 임의 URL 수집 경로를 만들지 않기 위해 존재한다.
CREATE TABLE news_sources (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  category VARCHAR(50) NOT NULL,
  name VARCHAR(100) NOT NULL,        -- 매체명. 화면·오디오 출처 표기에 쓴다
  feed_url TEXT NOT NULL UNIQUE,
  enabled BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_news_sources_category ON news_sources(category) WHERE enabled;

-- ⚠️ 이걸 빠뜨리면 42501 permission denied로 기능 전체가 죽는다.
--    library_saves가 실제로 이 문제로 죽어 있었다 (docs/SUPABASE_SETUP.md).
GRANT ALL ON news_sources TO service_role;

-- audiobooks 확장
ALTER TABLE audiobooks ADD COLUMN news_status VARCHAR(20) DEFAULT 'published';
ALTER TABLE audiobooks ADD COLUMN news_url TEXT;
ALTER TABLE audiobooks ADD COLUMN news_guid VARCHAR(255);

-- 어제 다룬 기사가 오늘 다시 들어오지 않게 한다.
-- RSS는 같은 기사를 며칠씩 반복 노출한다 — 이게 없으면 중복이 쌓인다.
CREATE UNIQUE INDEX idx_audiobooks_news_guid
  ON audiobooks(news_guid) WHERE news_guid IS NOT NULL;
```

`news_status`의 기본값을 `'published'`로 두는 이유: 기존 관리자 붙여넣기 행들이 전부 `NULL`이 되어 목록에서 사라지는 걸 막는다. 자동 생성분만 `store_news_item`에서 명시적으로 `'review'`를 넣는다.

`GET /api/news`에 `.eq("news_status", "published")` 필터를 추가한다.

---

## 6. 파일 단위 변경 계획

### 신규

| 파일 | 책임 | 대략 |
|---|---|---|
| `backend/news_sources.py` | RSS 수집. 피드 하나 실패해도 나머지는 계속한다 | ~80줄 |
| `backend/summarizer.py` | Claude 호출 + Pydantic 스키마 + 길이 검증 | ~120줄 |
| `backend/routes/briefing.py` | `POST /api/admin/briefing/run` 트리거 | ~90줄 |
| `.github/workflows/daily-briefing.yml` | cron | ~15줄 |

### 변경

| 파일 | 무엇을 |
|---|---|
| `backend/routes/news.py` | 정제 로직을 `_normalize_items()`로 추출(아래), `news_status` 필터, `store_news_item`에 `news_url`/`news_guid`/`news_status` 추가 |
| `backend/requirements.txt` | `anthropic`, `feedparser` |
| `backend/main.py` | `briefing` 라우터 등록 |
| `backend/state.py` | `BRIEFING_TRIGGER_SECRET` 검증 헬퍼 |
| `docs/SUPABASE_SETUP.md` | 위 스키마 + GRANT 절차 |
| `frontend/components/News/*` | 출처·원문 링크 노출 |
| `frontend/Admin/*` | 승인 탭 (기존 '발행 관리' 구조 재사용) |

### 중복 제거 — `_normalize_items` 추출

`_parse_news_payload`는 지금 두 가지 일을 한다: **JSON 파싱**과 **항목 정제**(citation artifact 제거, 제목 중복 제거, 필드 길이 제한). 자동 경로는 파싱이 필요 없지만 정제는 똑같이 필요하다.

```python
def _normalize_items(items: list[dict]) -> list[dict]:
    """title/content를 정제하고 중복 제목을 거른다. 붙여넣기 경로와
    자동 생성 경로가 같은 규칙을 통과하도록 여기 한 곳에 모은다."""

def _parse_news_payload(raw_text: str) -> list[dict]:
    """관리자 붙여넣기용. JSON을 읽어 _normalize_items에 넘긴다."""
```

두 경로가 갈리면 "붙여넣기는 걸러지는데 자동 생성은 안 걸러진다" 같은 일이 생긴다. 같은 지식이 두 곳에 있으면 안 된다(`development-guidelines.md` §4).

---

## 7. 실패 처리

기존 `_process_news_batch`의 원칙을 그대로 따른다.

| 실패 지점 | 처리 |
|---|---|
| RSS 피드 1개 실패 | 그 소스만 건너뛰고 `logger.exception`. 전체 중단 안 함 |
| 후보가 0건 | 아무것도 하지 않고 종료. **어제 뉴스를 지우지 않는다** |
| LLM 호출 실패 | SDK 기본 재시도(2회) → 그래도 실패면 그 카테고리 실패로 기록 |
| 요약이 400자 초과 | 한 번 재시도 → 그래도 초과면 그 항목만 버린다 |
| TTS 실패 | `content_jobs`가 원문을 들고 있으므로 관리자가 /admin에서 재시도 |
| 중복 실행 | `content_jobs`의 in-flight 체크 재사용 → 429 |

**핵심 원칙(기존 코드에서 그대로):** 새 묶음이 하나라도 성공한 뒤에만 이전 뉴스를 지운다. 새 뉴스가 없는 것보다 어제 뉴스라도 있는 게 낫다.

---

## 8. 테스트

프로젝트 관례상 동작을 검증하는 테스트를 함께 넣는다. 통과하지만 아무것도 검증하지 않는 테스트 사례가 있었으므로(`docs/troubleshooting/04-vacuous-delete-test.md`), 수정을 잠시 되돌려 실제로 실패하는지 확인한다.

```
backend/tests/test_news_sources.py
  - 피드 하나가 죽어도 나머지 후보가 수집된다
  - enabled=false 소스는 수집하지 않는다
backend/tests/test_summarizer.py
  - 400자를 넘는 요약은 재시도한다
  - url 없는 항목은 거부한다
  - source 없는 항목은 거부한다
backend/tests/test_briefing.py
  - 잘못된 토큰은 401
  - 처리 중이면 429
  - 후보 0건이면 기존 뉴스를 지우지 않는다
  - 자동 생성분은 news_status='review'로 저장된다
backend/tests/test_news.py (추가)
  - news_status='review'는 공개 목록에 안 나온다
  - _normalize_items가 두 경로에서 같게 동작한다
```

---

## 9. 지표

`retention-roadmap.md`의 지표는 전부 문서 전제라 뉴스 중심으로는 맞지 않는다. `product_events`에 이벤트만 추가해 기준선을 만든다 — 대시보드는 데이터가 쌓인 뒤에 붙인다.

| 이벤트 | 의미 |
|---|---|
| `briefing_generated` | 자동 생성 성공 (일 1회) |
| `briefing_published` | 관리자 승인 |
| `news_play_started` | 뉴스 재생 시작 |
| `news_play_completed` | 기사 끝까지 청취 |

이걸로 나중에 **일일 브리핑 청취율**과 **연속 청취일수**를 계산할 수 있다.

---

## 10. 구현 순서

각 단계는 독립적으로 배포 가능하다.

1. **DB 스키마 + `_normalize_items` 추출** — 동작 변화 없음. 정리와 기능 변경을 섞지 않는다(§11)
2. **`news_sources.py` + 수집 테스트** — 아직 아무 데도 안 붙임
3. **`summarizer.py` + 요약 테스트** — 로컬에서 실제 피드로 품질 확인
4. **`briefing.py` 트리거** — `workflow_dispatch`로 수동 실행해서 검증
5. **승인 게이트 + 관리자 UI**
6. **cron 활성화** — 여기서 처음으로 자동으로 돈다
7. **출처·링크 노출 (프론트)** — `static/sw.js`의 `CACHE_NAME` 올리는 것 잊지 않기

**되돌리기:** cron만 끄면 관리자 붙여넣기 경로가 그대로 살아 있다. 6번까지 가도 언제든 수동으로 돌아갈 수 있다.

---

## 11. 이 단계에서 하지 않는 것

명시적으로 범위 밖이다.

- 개인화 · 관심사 선택 · 사용자별 브리핑
- 카테고리 확장 (Step 1)
- 프롬프트 캐싱 (카테고리 2개 이상일 때)
- 유료화 · 가격 설계
- 프로젝트 이름 변경
- 문서 기능 축소
- 기사 본문 크롤링

---

## 결정 기록 (ADR)

**결정 1 — 스케줄러는 GitHub Actions cron**
맥락: fly.io는 배포마다 프로세스가 재시작되고 `auto_stop_machines='suspend'`다. 인프로세스 루프(`cleanup.py` 패턴)는 스케줄이 리셋되고 관측이 어렵다.
결정: 외부 cron이 HTTP 엔드포인트를 친다.
대안: 인프로세스 루프 + DB에 마지막 실행 시각 기록 — 코드베이스 일관성은 좋지만 관측과 수동 재실행이 없다.
결과: 배포·재시작에 영향받지 않고 실행 이력이 남는다. 대신 Actions cron의 지연(10~60분)을 여유 시간으로 흡수해야 한다.

**결정 2 — 기사 본문을 크롤링하지 않는다**
맥락: `extract_url.py`로 본문 추출이 이미 가능하지만, 2026년 한국에서 기사 전문 기반 AI 요약은 정부가 침해로 해석한 행위와 겹친다.
결정: RSS 피드의 title/description만 입력으로 쓴다.
대안: trafilatura로 본문 추출 — 요약 품질은 오르지만 법적 위치가 나빠진다.
결과: 요약 품질에 상한이 생긴다. 대신 소스 화이트리스트·짧은 요약·출처 표기와 함께 방어 가능한 구조가 된다.

**결정 3 — Batch API를 쓰지 않는다**
맥락: 50% 할인이지만 완료까지 최대 24시간이다.
결정: 동기 호출.
대안: Batch API — 월 $1.6 절감.
결과: 비용이 두 배지만 절대액이 월 $3 수준이고, 일일 브리핑에서 지연은 제품 실패다.
