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

---

## 🔐 3단계: Row Level Security (RLS) 정책 설정

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
