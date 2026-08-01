import httpx
import pytest
from unittest.mock import MagicMock, patch

import main
from push_notifications import WebPushException, send_background_job_ready


@pytest.fixture
def mock_supabase():
    with patch("auth.get_supabase_client") as get_client:
        client = MagicMock()
        get_client.return_value = client
        yield client


@pytest.mark.asyncio
async def test_push_subscription_requires_login():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app), base_url="http://test"
    ) as client:
        response = await client.post("/api/push/subscriptions", json={
            "endpoint": "https://push.example/subscription",
            "keys": {"p256dh": "public-key", "auth": "auth-key"},
        })

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


def test_ready_push_removes_only_expired_subscriptions(mock_supabase):
    mock_supabase.table("push_subscriptions").select().eq().execute.return_value = MagicMock(data=[
        {"endpoint": "https://push.example/expired", "p256dh": "p", "auth": "a"},
        {"endpoint": "https://push.example/temporary", "p256dh": "p", "auth": "a"},
    ])
    expired = WebPushException("gone", response=MagicMock(status_code=410))
    temporary = WebPushException("temporary", response=MagicMock(status_code=503))

    with patch("push_notifications.webpush", side_effect=[expired, temporary]), \
         patch("push_notifications.push_is_configured", return_value=True), \
         patch.dict("os.environ", {
             "VAPID_PRIVATE_KEY": "private-key",
             "VAPID_SUBJECT": "mailto:test@example.com",
         }):
        send_background_job_ready("user-1", "job-1")

    mock_supabase.table("push_subscriptions").delete().eq.assert_called_once_with(
        "endpoint", "https://push.example/expired"
    )


def test_ready_push_does_not_propagate_subscription_lookup_failure():
    with patch("push_notifications.push_is_configured", return_value=True), \
         patch("push_notifications.state._supabase_or_503", side_effect=RuntimeError("unavailable")):
        send_background_job_ready("user-1", "job-1")
