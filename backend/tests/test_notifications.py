import base64
import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

import main
from push_notifications import WebPushException, push_is_configured, send_background_job_ready


APPLE_ENDPOINT = "https://web.push.apple.com/QH2bkq"
GOOGLE_ENDPOINT = "https://fcm.googleapis.com/fcm/send/abc"
MOZILLA_ENDPOINT = "https://updates.push.services.mozilla.com/wpush/v2/abc"
WINDOWS_ENDPOINT = "https://wns2.notify.windows.com/w/?token=abc"


@pytest.fixture
def mock_supabase():
    with patch("auth.get_supabase_client") as get_client:
        client = MagicMock()
        get_client.return_value = client
        yield client


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,json_body", [
    ("post", "/api/push/subscriptions", {
        "endpoint": APPLE_ENDPOINT,
        "keys": {"p256dh": "public-key", "auth": "auth-key"},
    }),
    ("delete", "/api/push/subscriptions", {"endpoint": APPLE_ENDPOINT}),
    ("get", "/api/background-jobs/job-1", None),
])
async def test_push_routes_require_login(method, path, json_body):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app), base_url="http://test"
    ) as client:
        response = await client.request(method.upper(), path, json=json_body)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_push_config_hides_private_vapid_key_when_disabled():
    with patch.dict("os.environ", {}, clear=True):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app), base_url="http://test"
        ) as client:
            response = await client.get("/api/push/config")

    assert response.json() == {"enabled": False, "public_key": ""}


@pytest.mark.asyncio
async def test_background_job_status_hides_other_users_job(mock_supabase):
    mock_supabase.table().select().eq().eq().maybe_single().execute.return_value = MagicMock(data=None)

    with patch("state.require_user_id", return_value="user-2"):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app), base_url="http://test"
        ) as client:
            response = await client.get(
                "/api/background-jobs/job-1", headers={"Authorization": "Bearer token"}
            )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_background_job_status_returns_404_when_execute_returns_none(mock_supabase):
    # postgrest-py는 maybe_single()에 일치하는 행이 0개면 .execute() 자체가
    # None을 돌려준다(버전에 따른 동작, MagicMock(data=None)과는 다르다).
    # .data로 바로 접근하면 AttributeError가 나서 500으로 이어졌던 회귀를 재현한다.
    mock_supabase.table().select().eq().eq().maybe_single().execute.return_value = None

    with patch("state.require_user_id", return_value="user-2"):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app), base_url="http://test"
        ) as client:
            response = await client.get(
                "/api/background-jobs/job-1", headers={"Authorization": "Bearer token"}
            )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_push_subscription_upserts_for_authenticated_user(mock_supabase):
    mock_supabase.table().select().eq().limit().execute.return_value = MagicMock(data=[])

    with patch("state.require_user_id", return_value="user-1"), \
         patch("routes.notifications.enforce_rate_limit", create=True):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/push/subscriptions",
                headers={"Authorization": "Bearer token"},
                json={
                    "endpoint": GOOGLE_ENDPOINT,
                    "keys": {"p256dh": "public-key", "auth": "auth-key"},
                },
            )

    assert response.status_code == 200
    saved = mock_supabase.table().upsert.call_args.args[0]
    assert saved["user_id"] == "user-1"
    assert saved["endpoint"] == GOOGLE_ENDPOINT


@pytest.mark.asyncio
async def test_delete_push_subscription_is_scoped_to_user_and_endpoint(mock_supabase):
    with patch("state.require_user_id", return_value="user-1"):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app), base_url="http://test"
        ) as client:
            response = await client.request(
                "DELETE",
                "/api/push/subscriptions",
                headers={"Authorization": "Bearer token"},
                json={"endpoint": MOZILLA_ENDPOINT},
            )

    assert response.status_code == 200
    query = mock_supabase.table().delete()
    query.eq.assert_any_call("user_id", "user-1")
    query.eq().eq.assert_called_with("endpoint", MOZILLA_ENDPOINT)


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", [
    "http://fcm.googleapis.com/fcm/send/abc",
    "https://untrusted.invalid/subscription",
    "https://fcm.googleapis.com.evil.test/fcm/send/abc",
    "https://localhost/push",
    "https://127.0.0.1/push",
    "https://10.0.0.1/push",
    "https://169.254.169.254/latest/meta-data",
    "https://[::1]/push",
    "not-a-url",
])
async def test_push_subscription_rejects_malformed_or_untrusted_endpoint(mock_supabase, endpoint):
    with patch("state.require_user_id", return_value="user-1"), \
         patch("routes.notifications.enforce_rate_limit", create=True):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/push/subscriptions",
                headers={"Authorization": "Bearer token"},
                json={
                    "endpoint": endpoint,
                    "keys": {"p256dh": "public-key", "auth": "auth-key"},
                },
            )

    assert response.status_code == 422
    mock_supabase.table().upsert.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", [APPLE_ENDPOINT, GOOGLE_ENDPOINT, MOZILLA_ENDPOINT, WINDOWS_ENDPOINT])
async def test_push_subscription_accepts_supported_provider_endpoints(mock_supabase, endpoint):
    mock_supabase.table().select().eq().limit().execute.return_value = MagicMock(data=[])

    with patch("state.require_user_id", return_value="user-1"), \
         patch("routes.notifications.enforce_rate_limit", create=True):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/push/subscriptions",
                headers={"Authorization": "Bearer token"},
                json={
                    "endpoint": endpoint,
                    "keys": {"p256dh": "public-key", "auth": "auth-key"},
                },
            )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_push_subscription_caps_new_endpoints_at_five(mock_supabase):
    mock_supabase.table().select().eq().limit().execute.return_value = MagicMock(data=[
        {"endpoint": f"https://fcm.googleapis.com/fcm/send/{index}"} for index in range(5)
    ])

    with patch("state.require_user_id", return_value="user-1"), \
         patch("routes.notifications.enforce_rate_limit", create=True):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/push/subscriptions",
                headers={"Authorization": "Bearer token"},
                json={
                    "endpoint": APPLE_ENDPOINT,
                    "keys": {"p256dh": "public-key", "auth": "auth-key"},
                },
            )

    assert response.status_code == 409
    mock_supabase.table().upsert.assert_not_called()


@pytest.mark.asyncio
async def test_push_subscription_allows_existing_endpoint_at_cap(mock_supabase):
    existing = [
        {"endpoint": GOOGLE_ENDPOINT},
        *({"endpoint": f"https://fcm.googleapis.com/fcm/send/{index}"} for index in range(4)),
    ]
    mock_supabase.table().select().eq().limit().execute.return_value = MagicMock(data=existing)

    with patch("state.require_user_id", return_value="user-1"), \
         patch("routes.notifications.enforce_rate_limit", create=True):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/push/subscriptions",
                headers={"Authorization": "Bearer token"},
                json={
                    "endpoint": GOOGLE_ENDPOINT,
                    "keys": {"p256dh": "updated-key", "auth": "updated-auth"},
                },
            )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_push_subscription_registration_enforces_rate_limit(mock_supabase):
    with patch("state.require_user_id", return_value="user-1"), \
         patch("routes.notifications.enforce_rate_limit", create=True) as enforce:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app), base_url="http://test"
        ) as client:
            await client.post(
                "/api/push/subscriptions",
                headers={"Authorization": "Bearer token"},
                json={
                    "endpoint": GOOGLE_ENDPOINT,
                    "keys": {"p256dh": "public-key", "auth": "auth-key"},
                },
            )

    enforce.assert_called_once()
    assert enforce.call_args.kwargs == {"limit": 10, "window_sec": 600}


def _valid_vapid_environment():
    public_bytes = bytes.fromhex(
        "04"
        "6b17d1f2e12c4247f8bce6e563a440f277037d812deb33a0f4a13945d898c296"
        "4fe342e2fe1a7f9b8ee7eb4a7c0f9e162bce33576b315ececbb6406837bf51f5"
    )
    public_key = base64.urlsafe_b64encode(public_bytes).rstrip(b"=").decode()
    private_key = base64.urlsafe_b64encode(b"\0" * 31 + b"\1").rstrip(b"=").decode()
    return {
        "VAPID_PUBLIC_KEY": public_key,
        "VAPID_PRIVATE_KEY": private_key,
        "VAPID_SUBJECT": "mailto:ops@example.com",
    }


def test_push_config_requires_parseable_vapid_keys_and_valid_subject():
    vapid = MagicMock()
    with patch("push_notifications.Vapid", vapid, create=True), \
         patch("push_notifications.webpush", MagicMock()), \
         patch.dict("os.environ", _valid_vapid_environment(), clear=True):
        assert push_is_configured() is True
    vapid.from_string.assert_called_once()

    invalid_values = [
        {"VAPID_PUBLIC_KEY": "not-base64"},
        {"VAPID_PUBLIC_KEY": base64.urlsafe_b64encode(b"\x04" + b"p" * 63).decode()},
        {"VAPID_PUBLIC_KEY": base64.urlsafe_b64encode(b"\x04" + b"\0" * 64).decode()},
        {"VAPID_PUBLIC_KEY": base64.b64encode(bytes.fromhex(
            "04"
            "6b17d1f2e12c4247f8bce6e563a440f277037d812deb33a0f4a13945d898c296"
            "4fe342e2fe1a7f9b8ee7eb4a7c0f9e162bce33576b315ececbb6406837bf51f5"
        )).decode()},
        {"VAPID_PRIVATE_KEY": "not-a-private-key"},
        {"VAPID_SUBJECT": "mailto:not-an-address"},
        {"VAPID_SUBJECT": "http://example.com/contact"},
    ]
    for override in invalid_values:
        environment = {**_valid_vapid_environment(), **override}
        current_vapid = MagicMock()
        if override.get("VAPID_PRIVATE_KEY") == "not-a-private-key":
            current_vapid.from_string.side_effect = ValueError("invalid")
        with patch("push_notifications.Vapid", current_vapid, create=True), \
             patch("push_notifications.webpush", MagicMock()), \
             patch.dict("os.environ", environment, clear=True):
            assert push_is_configured() is False


def test_ready_push_is_bounded_and_sends_only_generic_payload(mock_supabase):
    subscriptions = [
        {"endpoint": f"https://fcm.googleapis.com/fcm/send/{index}", "p256dh": "p", "auth": "a"}
        for index in range(5)
    ]
    limit_query = mock_supabase.table("push_subscriptions").select().eq().limit
    limit_query().execute.return_value = MagicMock(data=subscriptions)
    limit_query.reset_mock()

    with patch("push_notifications.webpush") as send, \
         patch("push_notifications.push_is_configured", return_value=True), \
         patch.dict("os.environ", _valid_vapid_environment()):
        send_background_job_ready("user-1", "job-1")

    limit_query.assert_called_once_with(5)
    assert send.call_count == 5
    assert json.loads(send.call_args.kwargs["data"]) == {
        "type": "audiobook_ready",
        "job_id": "job-1",
    }


def test_ready_push_skips_legacy_untrusted_endpoint_at_send_boundary(mock_supabase):
    mock_supabase.table("push_subscriptions").select().eq().limit().execute.return_value = MagicMock(data=[
        {"endpoint": "https://127.0.0.1/private", "p256dh": "p", "auth": "a"},
        {"endpoint": GOOGLE_ENDPOINT, "p256dh": "p", "auth": "a"},
    ])

    with patch("push_notifications.webpush") as send, \
         patch("push_notifications.push_is_configured", return_value=True), \
         patch.dict("os.environ", _valid_vapid_environment()):
        send_background_job_ready("user-1", "job-1")

    assert send.call_count == 1
    assert send.call_args.kwargs["subscription_info"]["endpoint"] == GOOGLE_ENDPOINT


def test_ready_push_removes_only_expired_subscriptions(mock_supabase):
    mock_supabase.table("push_subscriptions").select().eq().limit().execute.return_value = MagicMock(data=[
        {
            "id": "subscription-1",
            "endpoint": APPLE_ENDPOINT,
            "p256dh": "p",
            "auth": "a",
            "updated_at": "2026-08-01T00:00:00Z",
        },
        {
            "id": "subscription-2",
            "endpoint": MOZILLA_ENDPOINT,
            "p256dh": "p",
            "auth": "a",
            "updated_at": "2026-08-01T00:00:00Z",
        },
    ])
    expired = WebPushException("gone", response=MagicMock(status_code=410))
    temporary = WebPushException("temporary", response=MagicMock(status_code=503))

    with patch("push_notifications.webpush", side_effect=[expired, temporary]), \
         patch("push_notifications.push_is_configured", return_value=True), \
         patch.dict("os.environ", _valid_vapid_environment()):
        send_background_job_ready("user-1", "job-1")

    delete_query = mock_supabase.table("push_subscriptions").delete()
    delete_query.eq.assert_called_once_with("user_id", "user-1")
    delete_query.eq().eq.assert_called_once_with("id", "subscription-1")
    delete_query.eq().eq().eq.assert_called_once_with(
        "updated_at", "2026-08-01T00:00:00Z"
    )
    cleanup_filters = repr(delete_query.mock_calls)
    assert APPLE_ENDPOINT not in cleanup_filters
    assert "p256dh" not in cleanup_filters
    assert "auth" not in cleanup_filters


def test_expired_subscription_cleanup_failure_does_not_stop_remaining_fanout(mock_supabase):
    mock_supabase.table("push_subscriptions").select().eq().limit().execute.return_value = MagicMock(data=[
        {
            "id": "subscription-1",
            "endpoint": APPLE_ENDPOINT,
            "p256dh": "p",
            "auth": "a",
            "updated_at": "2026-08-01T00:00:00Z",
        },
        {
            "id": "subscription-2",
            "endpoint": MOZILLA_ENDPOINT,
            "p256dh": "p",
            "auth": "a",
            "updated_at": "2026-08-01T00:00:00Z",
        },
    ])
    mock_supabase.table("push_subscriptions").delete().eq().eq().eq().execute.side_effect = RuntimeError(
        "cleanup unavailable"
    )
    expired = WebPushException("gone", response=MagicMock(status_code=410))

    with patch("push_notifications.webpush", side_effect=[expired, None]) as send, \
         patch("push_notifications.push_is_configured", return_value=True), \
         patch.dict("os.environ", _valid_vapid_environment()):
        send_background_job_ready("user-1", "job-1")

    assert send.call_count == 2


def test_ready_push_logs_only_redacted_counts_and_status_class(mock_supabase, caplog):
    caplog.set_level("INFO", logger="push_notifications")
    secret_endpoint = GOOGLE_ENDPOINT + "/secret-token"
    mock_supabase.table("push_subscriptions").select().eq().limit().execute.return_value = MagicMock(data=[
        {"endpoint": secret_endpoint, "p256dh": "secret-public", "auth": "secret-auth"},
    ])
    temporary = WebPushException("request contained " + secret_endpoint, response=MagicMock(status_code=503))

    with patch("push_notifications.webpush", side_effect=temporary), \
         patch("push_notifications.push_is_configured", return_value=True), \
         patch.dict("os.environ", _valid_vapid_environment()):
        send_background_job_ready("user-1", "job-1")

    logs = caplog.text
    assert "success=0" in logs
    assert "failed=1" in logs
    assert "status_class=5xx" in logs
    assert secret_endpoint not in logs
    assert "secret-public" not in logs
    assert "secret-auth" not in logs


def test_ready_push_does_not_propagate_subscription_lookup_failure(caplog):
    with patch("push_notifications.push_is_configured", return_value=True), \
         patch("push_notifications.state._supabase_or_503", side_effect=RuntimeError("private detail")):
        send_background_job_ready("user-1", "job-1")

    assert "private detail" not in caplog.text
