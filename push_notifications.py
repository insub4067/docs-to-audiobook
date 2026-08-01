import base64
import ipaddress
import json
import logging
import os
import re
from urllib.parse import urlsplit

import state


logger = logging.getLogger(__name__)
SUPPORTED_PUSH_HOSTS = {
    "web.push.apple.com",
    "fcm.googleapis.com",
    "updates.push.services.mozilla.com",
}
WINDOWS_PUSH_HOST = "notify.windows.com"

try:
    from cryptography.hazmat.primitives.asymmetric import ec
except ImportError:
    logger.warning("Web Push cryptography dependency is unavailable")
    ec = None

try:
    from pywebpush import WebPushException, webpush
except ImportError:
    logger.warning("Web Push dependency is unavailable")

    class WebPushException(Exception):
        def __init__(self, *args, response=None):
            super().__init__(*args)
            self.response = response

    webpush = None

try:
    from py_vapid import Vapid
except ImportError:
    logger.warning("VAPID dependency is unavailable")
    Vapid = None


def _decode_base64url(value: str) -> bytes:
    if re.fullmatch(r"[A-Za-z0-9_-]+={0,2}", value) is None:
        raise ValueError("invalid base64url")
    padding = "=" * ((4 - len(value) % 4) % 4)
    return base64.b64decode(value + padding, altchars=b"-_", validate=True)


def _valid_vapid_subject(subject: str) -> bool:
    if subject.startswith("mailto:"):
        address = subject.removeprefix("mailto:")
        return re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", address) is not None
    try:
        parsed = urlsplit(subject)
    except ValueError:
        return False
    return parsed.scheme == "https" and bool(parsed.hostname)


def is_supported_push_endpoint(endpoint: str) -> bool:
    try:
        parsed = urlsplit(endpoint)
        hostname = (parsed.hostname or "").lower()
        port = parsed.port
    except (TypeError, ValueError):
        return False
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
    ):
        return False
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        return False
    return (
        hostname in SUPPORTED_PUSH_HOSTS
        or hostname == WINDOWS_PUSH_HOST
        or hostname.endswith(f".{WINDOWS_PUSH_HOST}")
    )


def push_is_configured() -> bool:
    public_key = os.getenv("VAPID_PUBLIC_KEY", "")
    private_key = os.getenv("VAPID_PRIVATE_KEY", "")
    subject = os.getenv("VAPID_SUBJECT", "")
    if not webpush or not Vapid or not ec or not all((public_key, private_key, subject)):
        return False
    try:
        public_bytes = _decode_base64url(public_key)
        if len(public_bytes) != 65 or public_bytes[0] != 0x04:
            return False
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), public_bytes)
        Vapid.from_string(private_key)
    except Exception:
        logger.warning("Web Push configuration is invalid")
        return False
    if not _valid_vapid_subject(subject):
        logger.warning("Web Push configuration is invalid")
        return False
    return True


def send_background_job_ready(user_id: str, job_id: str) -> None:
    if not push_is_configured():
        return

    try:
        supabase = state._supabase_or_503()
        subscriptions = supabase.table("push_subscriptions").select(
            "id,endpoint,p256dh,auth,updated_at"
        ).eq("user_id", user_id).limit(5).execute().data or []
        success_count = 0
        failed_count = 0
        expired_count = 0
        for subscription in subscriptions:
            if not is_supported_push_endpoint(subscription.get("endpoint", "")):
                failed_count += 1
                logger.warning("Web Push delivery skipped error_type=UnsupportedEndpoint")
                continue
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
                success_count += 1
            except WebPushException as error:
                failed_count += 1
                status_code = getattr(getattr(error, "response", None), "status_code", None)
                if status_code in (404, 410):
                    expired_count += 1
                    try:
                        supabase.table("push_subscriptions").delete().eq(
                            "user_id", user_id
                        ).eq(
                            "id", subscription["id"]
                        ).eq(
                            "updated_at", subscription["updated_at"]
                        ).execute()
                    except Exception as cleanup_error:
                        logger.warning(
                            "Expired Web Push cleanup failed error_type=%s",
                            type(cleanup_error).__name__,
                        )
                status_class = f"{status_code // 100}xx" if isinstance(status_code, int) else "unknown"
                logger.warning("Web Push delivery failed status_class=%s", status_class)
            except Exception as error:
                failed_count += 1
                logger.warning("Web Push delivery failed error_type=%s", type(error).__name__)
        logger.info(
            "Web Push delivery summary success=%d failed=%d expired=%d",
            success_count,
            failed_count,
            expired_count,
        )
    except Exception as error:
        logger.warning("Web Push subscription lookup failed error_type=%s", type(error).__name__)
        return
