"""Authentication utilities for P2 features."""

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# JWT configuration
ALGORITHM = os.getenv("ALGORITHM", "HS256")
DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES = 525_600
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", str(DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES)))


def get_secret_key() -> str:
    secret_key = os.getenv("SECRET_KEY")
    if not secret_key:
        raise RuntimeError("SECRET_KEY 환경변수가 설정되어야 합니다.")
    return secret_key

# ============================================================
# JWT Token Functions
# ============================================================

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()

    # 코드베이스의 나머지(tts.py, system.py)가 aware datetime을 쓴다. utcnow()는
    # naive를 돌려줘 혼용이 됐고, 파이썬 3.12부터는 deprecated이기도 하다.
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, get_secret_key(), algorithm=ALGORITHM)
    return encoded_jwt

def decode_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(token, get_secret_key(), algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            return None
        return payload
    except JWTError:
        return None

# ============================================================
# Supabase Client Initialization
# ============================================================

# 만들어 둔 클라이언트를 역할별로 재사용한다. create_client()는 호출마다 새
# httpx 세션을 여는데, _supabase_or_503() 호출 지점이 49곳이고 요청 하나가
# 여러 번 부르는 경로도 있었다(library.py 9곳, audiobooks.py 7곳).
#
# 실패는 캐시하지 않는다 — 부팅 직후의 일시적 실패를 기억해 버리면 그 뒤로
# 영영 DB에 못 붙는다. 실패했으면 다음 호출이 다시 시도한다.
_clients: dict[bool, object] = {}


def reset_supabase_clients() -> None:
    """테스트가 환경변수를 바꿔가며 확인할 때 앞선 캐시가 새지 않게 한다."""
    _clients.clear()


def get_supabase_client(use_service_role: bool = False):
    """Initialize and return Supabase client."""
    cached = _clients.get(use_service_role)
    if cached is not None:
        return cached
    try:
        from supabase import create_client, Client

        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        if not url:
            raise ValueError("SUPABASE_URL must be set in .env")

        if use_service_role:
            if not service_key:
                print("WARNING: service_role key not set, falling back to anon key")
                key_to_use = key
            else:
                key_to_use = service_key
        else:
            if not key:
                raise ValueError("SUPABASE_KEY must be set in .env")
            key_to_use = key

        supabase: Client = create_client(url, key_to_use)
        _clients[use_service_role] = supabase
        return supabase
    except Exception as e:
        logger.warning("Failed to initialize Supabase client: %s", e)
        return None
