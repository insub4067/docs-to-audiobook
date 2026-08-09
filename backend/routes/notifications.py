import os
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

import state
from push_notifications import is_supported_push_endpoint, push_is_configured
from state import enforce_rate_limit


router = APIRouter()
MAX_PUSH_SUBSCRIPTIONS_PER_USER = 5


class PushSubscriptionKeys(BaseModel):
    p256dh: str = Field(min_length=1, max_length=2048)
    auth: str = Field(min_length=1, max_length=2048)


class PushSubscription(BaseModel):
    endpoint: str = Field(min_length=1, max_length=4096)
    keys: PushSubscriptionKeys


class PushSubscriptionDeletion(BaseModel):
    endpoint: str = Field(min_length=1, max_length=4096)


def _validate_push_endpoint(endpoint: str) -> str:
    if not is_supported_push_endpoint(endpoint):
        raise HTTPException(status_code=422, detail="지원하지 않는 Push endpoint입니다.")
    return endpoint


@router.get("/api/push/config")
async def push_config():
    enabled = push_is_configured()
    return {
        "enabled": enabled,
        "public_key": os.getenv("VAPID_PUBLIC_KEY", "") if enabled else "",
    }


@router.post("/api/push/subscriptions")
async def save_push_subscription(
    request: Request,
    payload: PushSubscription,
    authorization: str = Header(None),
):
    user_id = state.require_user_id(authorization)
    enforce_rate_limit(request, "push_subscription", limit=10, window_sec=600)
    endpoint = _validate_push_endpoint(payload.endpoint)
    supabase = state.supabase_or_503()
    subscriptions = supabase.table("push_subscriptions").select("endpoint").eq(
        "user_id", user_id
    ).limit(MAX_PUSH_SUBSCRIPTIONS_PER_USER + 1).execute().data or []
    is_existing = any(subscription.get("endpoint") == endpoint for subscription in subscriptions)
    if not is_existing and len(subscriptions) >= MAX_PUSH_SUBSCRIPTIONS_PER_USER:
        raise HTTPException(status_code=409, detail="등록할 수 있는 알림 기기 수를 초과했습니다.")

    supabase.table("push_subscriptions").upsert({
        "user_id": user_id,
        "endpoint": endpoint,
        "p256dh": payload.keys.p256dh,
        "auth": payload.keys.auth,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }, on_conflict="endpoint").execute()
    return {"ok": True}


@router.delete("/api/push/subscriptions")
async def delete_push_subscription(payload: PushSubscriptionDeletion, authorization: str = Header(None)):
    user_id = state.require_user_id(authorization)
    endpoint = _validate_push_endpoint(payload.endpoint)
    state.supabase_or_503().table("push_subscriptions").delete().eq(
        "user_id", user_id
    ).eq("endpoint", endpoint).execute()
    return {"ok": True}


@router.get("/api/background-jobs/{job_id}")
async def get_background_job_status(job_id: str, authorization: str = Header(None)):
    user_id = state.require_user_id(authorization)
    response = state.supabase_or_503().table("background_synthesis_jobs").select(
        "status,error,audiobook_id,completed_at"
    ).eq("id", job_id).eq("user_id", user_id).maybe_single().execute()
    # postgrest-py는 일치하는 행이 0개면 .execute()가 None을 돌려준다
    # (버전에 따른 동작). .data로 바로 접근하면 AttributeError.
    job = response.data if response else None
    if not job:
        raise HTTPException(status_code=404, detail="해당 작업을 찾을 수 없습니다.")
    return job
