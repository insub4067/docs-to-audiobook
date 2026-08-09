"""인증: 현재 사용자 조회 + 소셜 로그인.

제공자를 늘릴 때 손댈 곳을 한 군데로 모은다: 토큰을 검증해 공통 프로필로
바꾸는 함수를 하나 쓰고 SOCIAL_VERIFIERS에 등록하면 된다. 사용자 조회/생성과
토큰 발급은 제공자와 무관하게 공유된다.

계정 식별은 이메일 기준이다. 같은 이메일로 다른 제공자를 쓰면 같은 계정이
된다(의도된 동작).

NOTE: users 테이블에 google_id 컬럼이 제공자별로 박혀 있어 확장이 어렵다.
카카오/네이버/애플을 붙이기 전에 아래 마이그레이션을 권한다:
  ALTER TABLE users ADD COLUMN provider VARCHAR(20);
  ALTER TABLE users ADD COLUMN provider_id VARCHAR(255);
  CREATE UNIQUE INDEX idx_users_provider ON users(provider, provider_id);
그 전까지는 google_id만 채우고 나머지 제공자는 이메일로만 식별한다.
"""
import os
import logging
import uuid
from fastapi import APIRouter, Header, HTTPException

from state import _admin_emails

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/api/auth/me")
async def get_current_user(authorization: str = Header(None)):
    """Get current user info from JWT token."""
    try:
        from auth import decode_token, get_supabase_client

        if not authorization:
            raise HTTPException(status_code=401, detail="No authorization token")

        # Extract token from "Bearer <token>"
        token = authorization.split(" ")[-1] if " " in authorization else authorization
        payload = decode_token(token)

        if not payload:
            raise HTTPException(status_code=401, detail="Invalid token")

        user_id = payload.get("sub")
        supabase = get_supabase_client(use_service_role=True)

        response = supabase.table("users").select("*").eq("id", user_id).single().execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="User not found")

        user = response.data
        return {
            "id": user["id"],
            "email": user["email"],
            "full_name": user.get("full_name"),
            "avatar_url": user.get("avatar_url"),
            "is_admin": (user.get("email") or "").lower() in _admin_emails(),
            "created_at": user.get("created_at")
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Get user failed: %s", e)
        raise HTTPException(status_code=401, detail="Unauthorized")


def _verify_google(token_string: str) -> dict:
    """구글 ID 토큰을 검증해 공통 프로필로 변환한다."""
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token

    try:
        info = id_token.verify_oauth2_token(
            token_string, google_requests.Request(), os.getenv("GOOGLE_CLIENT_ID")
        )
    except Exception as e:
        logger.warning("Invalid Google token: %s", e)
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")

    return {
        "provider": "google",
        "provider_id": info.get("sub"),
        "email": info.get("email"),
        "full_name": info.get("name", ""),
        "avatar_url": info.get("picture"),
    }


# 새 제공자는 검증 함수를 만들어 여기에 등록한다.
# 예: "kakao": _verify_kakao, "naver": _verify_naver, "apple": _verify_apple
SOCIAL_VERIFIERS = {
    "google": _verify_google,
}


def _upsert_social_user(profile: dict) -> dict:
    """제공자와 무관하게 사용자를 찾거나 만든다."""
    from auth import get_supabase_client

    email = profile.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="이메일을 가져오지 못했습니다.")

    supabase = get_supabase_client(use_service_role=True)
    if not supabase:
        raise HTTPException(status_code=503, detail="사용자 저장소에 연결할 수 없습니다.")

    try:
        found = supabase.table("users").select("*").eq("email", email).single().execute()
        existing = found.data
    except Exception:
        existing = None

    if existing:
        return existing

    user_id = str(uuid.uuid4())
    row = {
        "id": user_id,
        "email": email,
        "full_name": profile.get("full_name") or "",
        "avatar_url": profile.get("avatar_url"),
    }
    # 제공자별 식별자 컬럼은 구글만 존재한다. 위 NOTE의 마이그레이션 전까지는
    # 나머지 제공자의 식별자를 저장하지 않는다.
    if profile.get("provider") == "google":
        row["google_id"] = profile.get("provider_id")

    supabase.table("users").insert(row).execute()
    return row


@router.post("/api/auth/social/{provider}")
async def social_login(provider: str, data: dict):
    """소셜 로그인. 제공자별 검증 후 우리 JWT를 발급한다."""
    from auth import create_access_token

    verifier = SOCIAL_VERIFIERS.get(provider)
    if not verifier:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 로그인 방식입니다: {provider}")

    token_string = data.get("token")
    if not token_string:
        raise HTTPException(status_code=400, detail="토큰이 필요합니다.")

    try:
        profile = verifier(token_string)
        user = _upsert_social_user(profile)
        return {
            "access_token": create_access_token({"sub": user["id"]}),
            "token_type": "bearer",
            "user": {
                "id": user.get("id"),
                "email": user.get("email"),
                "full_name": user.get("full_name"),
                "avatar_url": user.get("avatar_url"),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Social login failed provider=%s: %s", provider, e)
        raise HTTPException(status_code=500, detail="로그인에 실패했습니다.")
