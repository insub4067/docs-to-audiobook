import json
import os

import state

try:
    from pywebpush import WebPushException, webpush
except ImportError:
    class WebPushException(Exception):
        def __init__(self, *args, response=None):
            super().__init__(*args)
            self.response = response

    webpush = None


def push_is_configured() -> bool:
    return all(os.getenv(name) for name in (
        "VAPID_PUBLIC_KEY",
        "VAPID_PRIVATE_KEY",
        "VAPID_SUBJECT",
    ))


def send_background_job_ready(user_id: str, job_id: str) -> None:
    if not push_is_configured():
        return

    try:
        supabase = state._supabase_or_503()
        subscriptions = supabase.table("push_subscriptions").select(
            "endpoint,p256dh,auth"
        ).eq("user_id", user_id).execute().data or []
        for subscription in subscriptions:
            try:
                webpush(
                    subscription_info={
                        "endpoint": subscription["endpoint"],
                        "keys": {
                            "p256dh": subscription["p256dh"],
                            "auth": subscription["auth"],
                        },
                    },
                    data=json.dumps({"type": "audiobook_ready", "job_id": job_id}),
                    vapid_private_key=os.environ["VAPID_PRIVATE_KEY"],
                    vapid_claims={"sub": os.environ["VAPID_SUBJECT"]},
                    ttl=86400,
                    timeout=10,
                )
            except WebPushException as error:
                status_code = getattr(getattr(error, "response", None), "status_code", None)
                if status_code in (404, 410):
                    supabase.table("push_subscriptions").delete().eq(
                        "endpoint", subscription["endpoint"]
                    ).execute()
            except Exception:
                continue
    except Exception:
        return
