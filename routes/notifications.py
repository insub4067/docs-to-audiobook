import os
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

import state
from push_notifications import push_is_configured


router = APIRouter()


class PushSubscriptionKeys(BaseModel):
    p256dh: str = Field(min_length=1, max_length=2048)
    auth: str = Field(min_length=1, max_length=2048)


class PushSubscription(BaseModel):
    endpoint: str = Field(min_length=1, max_length=4096)
    keys: PushSubscriptionKeys


class PushSubscriptionDeletion(BaseModel):
    endpoint: str = Field(min_length=1, max_length=4096)


@router.get("/api/push/config")
async def push_config():
    enabled = push_is_configured()
    return {
        "enabled": enabled,
        "public_key": os.getenv("VAPID_PUBLIC_KEY", "") if enabled else "",
    }


@router.post("/api/push/subscriptions")
async def save_push_subscription(payload: PushSubscription, authorization: str = Header(None)):
    user_id = state.require_user_id(authorization)
    state._supabase_or_503().table("push_subscriptions").upsert({
        "user_id": user_id,
        "endpoint": str(payload.endpoint),
        "p256dh": payload.keys.p256dh,
        "auth": payload.keys.auth,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }, on_conflict="endpoint").execute()
    return {"ok": True}


@router.delete("/api/push/subscriptions")
async def delete_push_subscription(payload: PushSubscriptionDeletion, authorization: str = Header(None)):
    user_id = state.require_user_id(authorization)
    state._supabase_or_503().table("push_subscriptions").delete().eq(
        "user_id", user_id
    ).eq("endpoint", payload.endpoint).execute()
    return {"ok": True}


@router.get("/api/background-jobs/{job_id}")
async def get_background_job_status(job_id: str, authorization: str = Header(None)):
    user_id = state.require_user_id(authorization)
    job = state._supabase_or_503().table("background_synthesis_jobs").select(
        "status,error,audiobook_id,completed_at"
    ).eq("id", job_id).eq("user_id", user_id).maybe_single().execute().data
    if not job:
        raise HTTPException(status_code=404, detail="해당 작업을 찾을 수 없습니다.")
    return job
