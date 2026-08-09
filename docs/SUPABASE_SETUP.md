# 🚀 Supabase 설정 가이드 (P2)

Supabase를 사용하여 사용자 인증, 데이터베이스, 오디오북 스토리지를 관리합니다.

## 📋 준비 사항

- Supabase 계정 (https://supabase.com)
- Google OAuth 앱 (선택사항, OAuth 인증 사용 시)

---

## 🔧 1단계: Supabase 프로젝트 생성

### 1.1 프로젝트 생성
```bash
1. https://supabase.com 접속
2. "New Project" 클릭
3. 프로젝트명: "docs-to-audiobook" 
4. 데이터베이스 비밀번호: 강력한 비밀번호 설정
5. 지역: 가장 가까운 지역 선택 (예: Asia Pacific - Singapore)
6. "Create new project" 클릭
```

### 1.2 프로젝트 설정 정보 저장
생성 후 다음 정보를 `.env` 파일에 저장:

```
# .env 파일
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_JWT_SECRET=your-jwt-secret-from-project-settings
# 쉼표로 구분한 관리자 계정 이메일. 이 값이 없으면 /admin 접근이 모두 차단됩니다.
ADMIN_EMAILS=admin@example.com
```

---

## 🗄️ 2단계: 데이터베이스 테이블 생성

Supabase 대시보드 → SQL Editor에서 다음 쿼리 실행:

### 2.1 사용자 테이블
```sql
CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email VARCHAR(255) UNIQUE NOT NULL,
  full_name VARCHAR(255),
  password_hash VARCHAR(255),
  google_id VARCHAR(255) UNIQUE,
  avatar_url TEXT,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_google_id ON users(google_id);
```

### 2.2 오디오북 테이블
```sql
CREATE TABLE audiobooks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title VARCHAR(255) NOT NULL,
  file_name VARCHAR(255),
  duration_seconds INTEGER,
  created_at TIMESTAMP DEFAULT NOW(),
  storage_path VARCHAR(500) NOT NULL
);

CREATE INDEX idx_audiobooks_user_id ON audiobooks(user_id);
```

### 2.3 재생 기록 테이블
```sql
CREATE TABLE playback_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  audiobook_id UUID NOT NULL REFERENCES audiobooks(id) ON DELETE CASCADE,
  current_time_seconds INTEGER DEFAULT 0,
  playback_speed DECIMAL(3,2) DEFAULT 1.0,
  repeat_mode VARCHAR(20) DEFAULT 'off',
  last_played_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_playback_history_user_id ON playback_history(user_id);
CREATE UNIQUE INDEX idx_playback_history_unique ON playback_history(user_id, audiobook_id);
```

### 2.4 제품 이벤트 테이블
```sql
CREATE TABLE product_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  event_name VARCHAR(50) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_product_events_created_at ON product_events(created_at);
CREATE INDEX idx_product_events_user_id ON product_events(user_id);
```

관리자 대시보드는 이 테이블의 생성 시작·완료·실패·재생 시작 이벤트만 집계하며, 문서 내용이나 제목은 저장하지 않는다.

### 2.5 관리자 대용량 백그라운드 작업 테이블

관리자가 10MB를 넘는 문서를 올리면 서버가 브라우저와 무관하게 완료까지 처리한다(`docs/large-admin-background-jobs.md` 참고). 원본 파일이 아니라 이미 추출된 텍스트를 `source_text`에 저장한다 — 원본 PDF를 Storage에 올렸다가 워커가 다시 내려받아 재추출하는 구조보다 단순하고, PDF보다 텍스트가 훨씬 작아 대용량 Storage 업로드의 신뢰성 문제도 피한다. 완료·실패 후에는 `source_text`를 비워 원문을 남기지 않는다.

```sql
CREATE TABLE background_synthesis_jobs (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title VARCHAR(255) NOT NULL,
  source_text TEXT,
  voice VARCHAR(100) NOT NULL,
  rate VARCHAR(20) NOT NULL,
  pitch VARCHAR(20) NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'queued',
  error TEXT,
  audiobook_id UUID REFERENCES audiobooks(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at TIMESTAMPTZ
);

CREATE INDEX idx_background_jobs_status ON background_synthesis_jobs(status);
```

`id`는 애플리케이션이 생성해 넣으므로 기본값을 두지 않는다. `status`는 `queued` → `processing` → `completed`/`error`로 전이한다.

서버(service role)만 이 테이블을 읽고 쓴다. anon/authenticated 키로 직접 접근할 이유가 없으므로 RLS는 활성화만 해두고 별도 정책은 만들지 않는다 — 정책이 없으면 service role을 제외한 모든 요청이 기본적으로 거부된다.

```sql
ALTER TABLE background_synthesis_jobs ENABLE ROW LEVEL SECURITY;

GRANT SELECT, INSERT, UPDATE ON background_synthesis_jobs TO service_role;
```

서버는 진행 중 작업 조회·등록·상태 갱신만 수행하므로 `service_role`에도 이 세 권한만 부여한다.
RLS 우회 여부와 별개로 Data API 접근에는 테이블 `GRANT`가 필요하다.

### 2.6 완료 알림 구독 테이블

관리자 대용량 작업의 완료 Web Push 구독은 `push_subscriptions`에 저장한다. 다음 SQL을
`add_push_subscriptions` migration으로 적용한다.

```sql
create table public.push_subscriptions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  endpoint text not null unique,
  p256dh text not null,
  auth text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index push_subscriptions_user_id_idx on public.push_subscriptions(user_id);
alter table public.push_subscriptions enable row level security;
revoke all on table public.push_subscriptions from anon, authenticated;
grant select, insert, update, delete on table public.push_subscriptions to service_role;
```

브라우저는 Supabase에 직접 접근하지 않는다. 인증된 애플리케이션 API가 `service_role`로
현재 사용자의 구독만 등록·해제하고, 서버가 완료 통지를 보낼 때만 읽는다. 따라서 RLS는
활성화하되 anon/authenticated 정책과 권한을 두지 않는다.

적용 후에는 다음 SQL의 네 값이 모두 `true`인지 확인한다.

```sql
select
  has_table_privilege('service_role', 'public.push_subscriptions', 'SELECT'),
  has_table_privilege('service_role', 'public.push_subscriptions', 'INSERT'),
  has_table_privilege('service_role', 'public.push_subscriptions', 'UPDATE'),
  has_table_privilege('service_role', 'public.push_subscriptions', 'DELETE');
```

### 2.7 라이브러리 저장 테이블

서점(라이브러리)에서 "서재에 저장"한 작품을 사용자별로 기록한다. 한 사용자가 같은 작품을
중복 저장하지 않도록 `(user_id, audiobook_id)`에 유니크 제약을 둔다(서버가 `upsert`를 쓴다).

```sql
create table public.library_saves (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  audiobook_id uuid not null references public.audiobooks(id) on delete cascade,
  created_at timestamptz not null default now(),
  unique (user_id, audiobook_id)
);

create index library_saves_user_id_idx on public.library_saves(user_id);
alter table public.library_saves enable row level security;
revoke all on table public.library_saves from anon, authenticated;
grant select, insert, update, delete on table public.library_saves to service_role;
```

⚠️ 이 테이블은 처음 만들 때 `GRANT`가 통째로 빠져 있었고, 그 탓에 "서재에 저장" 기능
전체가 프로덕션에서 `42501 permission denied`로 500을 냈다. 테이블만 만들고 권한을 주지
않으면 RLS 우회 여부와 무관하게 Data API 접근이 거부되므로, 위 `grant`를 반드시 함께
실행할 것. 서버는 조회·저장(upsert)·저장취소(delete)를 하므로 네 권한이 모두 필요하다.

적용 후에는 다음 SQL의 네 값이 모두 `true`인지 확인한다.

```sql
select
  has_table_privilege('service_role', 'public.library_saves', 'SELECT'),
  has_table_privilege('service_role', 'public.library_saves', 'INSERT'),
  has_table_privilege('service_role', 'public.library_saves', 'UPDATE'),
  has_table_privilege('service_role', 'public.library_saves', 'DELETE');
```

### 2.8 콘텐츠 등록 작업 테이블

관리자가 경제 뉴스나 라이브러리 작품을 등록하면 합성이 끝나기 전까지의 상태를 여기에 남긴다.
**원문(`source_text`)을 합성 전에 먼저 저장하는 것이 이 테이블의 존재 이유다.** 예전에는
합성이 실패하면 `audiobooks` 행이 아예 만들어지지 않아 서버 로그 말고는 아무 흔적도 남지
않았고, 관리자는 무엇이 왜 실패했는지 알 수도 다시 시도할 수도 없었다.

뉴스와 라이브러리는 "제목 + 본문 + 메타데이터를 TTS로 합성해 audiobooks에 넣는다"는 점이
같아서 `kind`로만 구분하고 같은 테이블·같은 처리 경로(`backend/routes/content_jobs.py`)를 쓴다.

콘텐츠가 완성되면 이 행은 삭제한다 — 완성된 결과물은 `audiobooks`에 있고, 여기 남겨두면
"등록 작업" 목록이 완료 항목으로 계속 불어난다. 따라서 이 테이블에 남아 있는 행은
언제나 "아직 안 끝났거나 실패한 것"뿐이다.

```sql
create table public.content_jobs (
  id uuid primary key,
  kind varchar(20) not null,
  admin_user_id uuid not null references public.users(id) on delete cascade,
  title varchar(255) not null,
  source_text text not null,
  metadata jsonb not null default '{}'::jsonb,
  status varchar(20) not null default 'queued',
  error text,
  created_at timestamptz not null default now()
);

create index content_jobs_status_idx on public.content_jobs(status);
alter table public.content_jobs enable row level security;
revoke all on table public.content_jobs from anon, authenticated;
grant select, insert, update, delete on table public.content_jobs to service_role;
```

`id`는 애플리케이션이 만들어 넣으므로 기본값을 두지 않는다. `kind`는 `news` 또는 `library`다.
`status`는 `queued` → `processing` → (성공 시 행 삭제 / 실패 시 `error`)로 전이한다.
`metadata`에는 title/content를 뺀 나머지 필드가 통째로 들어가고(뉴스는 카테고리·출처,
라이브러리는 판본·번역자·이용조건 등), 합성이 끝나면 `audiobooks`의 해당 컬럼으로 옮겨간다.

진행률은 이 테이블에 저장하지 않는다 — 청크마다 UPDATE를 날리면 긴 경전 하나에 수백 번의
쓰기가 생긴다. 서버 프로세스 메모리에만 두고 목록 응답에 얹어 준다(재시작하면 사라지지만,
그때는 `status`가 진실이고 진행률은 아예 표시하지 않는다).

`GRANT`를 빠뜨리면 §2.7의 `library_saves`가 그랬듯 `42501 permission denied`로 등록 기능
전체가 500을 낸다. 적용 후 다음 SQL의 네 값이 모두 `true`인지 확인한다.

```sql
select
  has_table_privilege('service_role', 'public.content_jobs', 'SELECT'),
  has_table_privilege('service_role', 'public.content_jobs', 'INSERT'),
  has_table_privilege('service_role', 'public.content_jobs', 'UPDATE'),
  has_table_privilege('service_role', 'public.content_jobs', 'DELETE');
```

### 2.9 조용한 실패 테이블

클라이언트가 사용자 경험을 위해 삼킨 실패를 한 줄씩 남긴다. **이 테이블이 없던 동안
`playback_history`가 몇 주간 통째로 비어 있었는데 아무도 몰랐다** — 클라이언트는 저장이
500을 내도 재생을 계속했고, 그 실패는 사용자 기기의 console에만 남았기 때문이다.

`user_id`가 NULL일 수 있는 것은 의도적이다. 가입만 하고 아무것도 하지 않은 사용자가
무엇에 걸려 떠났는지가 정확히 여기서 알고 싶은 것이라, 비로그인 체험 중의 실패를
버리면 이 테이블을 만든 이유의 절반이 사라진다.

```sql
create table public.client_errors (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.users(id) on delete set null,
  scope varchar(40) not null,
  message text not null,
  app_version varchar(60),
  created_at timestamptz not null default now()
);

create index client_errors_created_at_idx on public.client_errors(created_at desc);
alter table public.client_errors enable row level security;
revoke all on table public.client_errors from anon, authenticated;
grant select, insert, delete on table public.client_errors to service_role;
```

### 2.9 TTS 사용량 테이블

가격을 정하려면 "사용자 한 명이 얼마를 쓰는가"를 알아야 한다. `product_events`에는 `user_id`와 `event_name`밖에 없어 그 계산이 불가능했다. 추정 단가가 아니라 **원단위(문자 수)만** 저장한다 — 단가는 바뀌고 공급자마다 다르므로 금액 계산은 조회 시점에 한다(`backend/routes/system.py`의 `usd_per_million_chars`).

```sql
create table public.synthesis_usage (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.users(id) on delete set null,
  provider varchar(30) not null,
  voice varchar(100) not null,
  characters integer not null,
  audio_seconds numeric(10, 2),
  elapsed_seconds numeric(10, 2),
  succeeded boolean not null default true,
  created_at timestamptz not null default now()
);

create index synthesis_usage_created_at_idx on public.synthesis_usage(created_at desc);
create index synthesis_usage_user_id_idx on public.synthesis_usage(user_id);
alter table public.synthesis_usage enable row level security;
revoke all on table public.synthesis_usage from anon, authenticated;
grant select, insert, delete on table public.synthesis_usage to service_role;
```

실패한 합성도 남긴다(`succeeded = false`). 문자는 이미 소모됐으므로 성공만 세면 실비용을 과소평가한다 — Edge TTS는 호스트에 따라 간헐적으로 실패한다.

`scope`는 `backend/routes/system.py`의 `CLIENT_ERROR_LABELS`에 있는 값만 받는다
(`playback_save` / `product_event` / `generation` / `cloud_sync` / `default_book`).
아무 문자열이나 받으면 오타 하나로 지표가 두 갈래로 갈라지기 때문이다.

관리자 대시보드의 "조용한 실패" 카드에서 최근 7일치를 볼 수 있다. 여기 안 실리면
로그에만 쌓이고 아무도 보지 않으므로, 테이블만 만들고 끝내면 의미가 없다.

---

## 🔐 3단계: Row Level Security (RLS) 정책 설정

### 3.0 ⚠️ 권한부터 회수한다 — RLS는 두 번째 방어선이다

**RLS 정책을 믿기 전에 `GRANT`부터 확인할 것.** 이 앱은 Supabase Auth를 쓰지 않고
자체 JWT를 쓰기 때문에, 아래 정책들의 `auth.uid()`는 anon 키로 접근하면 언제나 NULL이다.
그래서 정책이 "우연히" 모든 접근을 거부한다. 정책을 하나만 잘못 고치면 `users` 테이블이
통째로 열린다는 뜻이기도 하다.

서버는 모든 경로에서 service_role 키만 쓰고(`auth.get_supabase_client(use_service_role=True)`),
프론트엔드는 Supabase를 직접 호출하지 않는다. 즉 anon/authenticated 권한은 아무도 쓰지 않는다.

```sql
revoke select, insert, update, delete on table public.users from anon, authenticated;
revoke select, insert, update, delete on table public.audiobooks from anon, authenticated;
revoke select, insert, update, delete on table public.folders from anon, authenticated;
revoke select, insert, update, delete on table public.playback_history from anon, authenticated;
revoke insert on table public.product_events from authenticated;
```

적용 후 다음 쿼리가 **빈 결과**여야 한다.

```sql
select table_name, grantee, privilege_type
from information_schema.role_table_grants
where table_schema='public'
  and grantee in ('anon','authenticated')
  and privilege_type in ('SELECT','INSERT','UPDATE','DELETE');
```

새 테이블을 만들 때도 `revoke all ... from anon, authenticated`를 잊지 말 것.
`GRANT`를 반대로 빠뜨리면 `42501 permission denied`로 기능 전체가 500을 낸다
(§2.7의 `library_saves`가 실제로 그랬다).

### 3.1 이하: 각 테이블별 RLS 정책

각 테이블별로 보안 정책 활성화:

### 3.1 사용자 테이블 정책
```sql
-- 사용자는 자신의 데이터만 조회/수정 가능
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own data" ON users
  FOR SELECT USING (auth.uid() = id);

CREATE POLICY "Users can update own data" ON users
  FOR UPDATE USING (auth.uid() = id);
```

### 3.2 오디오북 테이블 정책
```sql
ALTER TABLE audiobooks ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own audiobooks" ON audiobooks
  FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own audiobooks" ON audiobooks
  FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete own audiobooks" ON audiobooks
  FOR DELETE USING (auth.uid() = user_id);
```

### 3.3 재생 기록 테이블 정책
```sql
ALTER TABLE playback_history ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own history" ON playback_history
  FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can update own history" ON playback_history
  FOR UPDATE USING (auth.uid() = user_id);
```

### 3.4 제품 이벤트 테이블 정책
```sql
ALTER TABLE product_events ENABLE ROW LEVEL SECURITY;

GRANT SELECT, INSERT ON product_events TO service_role;

CREATE POLICY "Users can insert own events" ON product_events
  FOR INSERT WITH CHECK (auth.uid() = user_id);
```

---

## 💾 4단계: Storage 설정

오디오북 파일 저장소 생성:

```bash
1. Supabase 대시보드 → Storage
2. "New bucket" 클릭
3. Bucket name: "audiobooks"
4. Privacy: Private 선택
5. "Create bucket" 클릭
```

Storage 정책 설정:
```sql
-- 사용자는 자신의 오디오북만 접근 가능
UPDATE storage.buckets SET public = false WHERE name = 'audiobooks';
```

---

## 🔑 5단계: Google OAuth 설정 (선택)

### 5.1 Google Cloud Console
```bash
1. https://console.cloud.google.com 접속
2. 새 프로젝트 생성: "docs-to-audiobook"
3. "OAuth 2.0 클라이언트 ID" 생성
4. 애플리케이션 유형: "웹 애플리케이션"
5. 승인된 리디렉션 URI 추가:
   - https://docs-to-audiobook.onrender.com/api/auth/google/callback
   - http://localhost:8000/api/auth/google/callback (로컬 테스트용)
```

### 5.2 Supabase에서 Google 공급자 활성화
```bash
1. Supabase 대시보드 → Authentication
2. "Providers" 탭 → Google
3. Enable Google 선택
4. Client ID, Client Secret 입력
5. Save
```

---

## 📝 6단계: 환경변수 설정

`.env` 파일 생성:

```env
# Supabase
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_JWT_SECRET=your-jwt-secret-from-project-settings

# JWT
SECRET_KEY=your-secret-key-for-token-signing
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=525600

# Google OAuth (선택)
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret

# Environment
ENVIRONMENT=development
```

---

## 🧪 7단계: 연결 테스트

FastAPI 백엔드에서:

```python
from supabase import create_client, Client

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(url, key)

# 테스트
response = supabase.table("users").select("*").limit(1).execute()
print(response)
```

---

## ✅ 체크리스트

- [ ] Supabase 프로젝트 생성
- [ ] `.env` 파일에 Supabase 키 저장
- [ ] 데이터베이스 테이블 생성
- [ ] RLS 정책 설정
- [ ] Storage bucket 생성
- [ ] Google OAuth 설정 (선택)
- [ ] 백엔드 연결 테스트

---

## 📚 참고 자료

- [Supabase 공식 문서](https://supabase.com/docs)
- [Supabase Python 클라이언트](https://github.com/supabase-community/supabase-py)
- [FastAPI + Supabase](https://supabase.com/docs/guides/integrations/fastapi)

---

## 소셜 로그인 제공자 추가하기 (카카오 / 네이버 / 애플)

이메일 로그인은 제거했다. 소셜 로그인만 취급하며, 제공자를 늘릴 때
손대는 곳은 아래 네 군데뿐이다.

### 1. 스키마 마이그레이션 (선행 필요)

현재 `users` 테이블은 `google_id` 컬럼이 제공자별로 박혀 있어 제공자마다
컬럼이 늘어난다. 두 번째 제공자를 붙이기 전에 일반화한다.

```sql
ALTER TABLE users ADD COLUMN provider VARCHAR(20);
ALTER TABLE users ADD COLUMN provider_id VARCHAR(255);
CREATE UNIQUE INDEX idx_users_provider ON users(provider, provider_id);

-- 기존 구글 사용자 이관
UPDATE users SET provider = 'google', provider_id = google_id
WHERE google_id IS NOT NULL;
```

그 뒤 `main.py`의 `_upsert_social_user()`에서 google_id 특수 처리를 지우고
provider/provider_id를 쓰도록 바꾼다.

### 2. 서버: 검증 함수 추가 (main.py)

토큰을 검증해 공통 프로필로 바꾸는 함수를 만들고 `SOCIAL_VERIFIERS`에 등록한다.
반환 형식은 제공자와 무관하게 동일하다.

```python
def _verify_kakao(token_string: str) -> dict:
    # 카카오 API로 토큰 검증 후
    return {
        "provider": "kakao",
        "provider_id": ...,
        "email": ...,
        "full_name": ...,
        "avatar_url": ...,
    }

SOCIAL_VERIFIERS = {
    "google": _verify_google,
    "kakao": _verify_kakao,
}
```

사용자 조회/생성과 JWT 발급은 `_upsert_social_user()`와
`/api/auth/social/{provider}`가 공통으로 처리하므로 건드릴 필요가 없다.

### 3. 서버: 클라이언트 키 노출 (main.py의 `/api/config`)

```python
providers = {
    "google": os.getenv("GOOGLE_CLIENT_ID", ""),
    "kakao": os.getenv("KAKAO_JS_KEY", ""),
}
```

값이 빈 제공자는 클라이언트가 알아서 건너뛴다.

### 4. 클라이언트: 버튼 렌더 (static/app.js의 `SOCIAL_PROVIDERS`)

```js
kakao: {
    async render(slot, jsKey) {
        // 버튼을 그리고, 인증 성공 시:
        completeSocialLogin("kakao", token);
    }
}
```

`completeSocialLogin()`이 `/api/auth/social/{provider}`로 토큰을 넘겨
세션을 만드는 공통 경로다. 제공자마다 다시 구현할 필요가 없다.

### 참고: 제공자별 주의점

- **애플**: 이메일 가리기(private relay)를 쓰면 실제 이메일이 오지 않는다.
  계정 식별을 이메일에만 의존하면 안 되므로 위 1번 마이그레이션이 특히 중요하다.
- **카카오**: 이메일이 선택 동의 항목이라 없을 수 있다. 같은 이유로 provider_id가 필요하다.
- 현재 계정 식별은 이메일 기준이다. 같은 이메일로 다른 제공자를 쓰면 같은
  계정이 된다(의도된 동작).
