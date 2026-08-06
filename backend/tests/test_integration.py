import pytest
import httpx
from unittest.mock import patch, MagicMock
from main import app

@pytest.fixture
def mock_supabase():
    with patch("auth.get_supabase_client") as mock_get_client:
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        yield mock_client

@pytest.fixture
def mock_auth():
    with patch("routes.audiobooks.require_user_id") as mock_req_user:
        mock_req_user.return_value = "test_user_id"
        yield mock_req_user

@pytest.mark.asyncio
async def test_get_audiobooks_success(mock_supabase, mock_auth):
    # Mock supabase response for selecting audiobooks
    mock_supabase.table().select().eq().eq().eq().order().execute.return_value = MagicMock(
        data=[{"id": "book1", "title": "Test Book", "status": "ready"}]
    )
    
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Provide dummy token to bypass preliminary checks if any, though mocked auth handles it
        response = await client.get("/api/audiobooks", headers={"Authorization": "Bearer fake_token"})
        
        assert response.status_code == 200
        data = response.json()
        assert "audiobooks" in data
        assert len(data["audiobooks"]) == 1
        assert data["audiobooks"][0]["title"] == "Test Book"

@pytest.mark.asyncio
async def test_create_audiobook_without_folder(mock_supabase, mock_auth):
    mock_supabase.table().insert().execute.return_value = MagicMock(data=[{"id": "book1"}])
    mock_supabase.storage.from_().create_signed_upload_url.return_value = {"signed_url": "https://x"}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/audiobooks", json={"title": "제목"}, headers={"Authorization": "Bearer fake_token"},
        )

    assert response.status_code == 200
    inserted = mock_supabase.table().insert.call_args[0][0]
    assert inserted["folder_id"] is None


@pytest.mark.asyncio
async def test_create_audiobook_with_valid_folder(mock_supabase, mock_auth):
    folders_table = MagicMock()
    folders_table.select().eq().eq().execute.return_value = MagicMock(data=[{"id": "f1"}])

    audiobooks_table = MagicMock()
    audiobooks_table.insert().execute.return_value = MagicMock(data=[{"id": "book1"}])

    def table_side_effect(name):
        return {"folders": folders_table, "audiobooks": audiobooks_table}[name]

    mock_supabase.table.side_effect = table_side_effect
    mock_supabase.storage.from_().create_signed_upload_url.return_value = {"signed_url": "https://x"}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/audiobooks",
            json={"title": "제목", "folder_id": "f1"},
            headers={"Authorization": "Bearer fake_token"},
        )

    assert response.status_code == 200
    inserted = audiobooks_table.insert.call_args[0][0]
    assert inserted["folder_id"] == "f1"


@pytest.mark.asyncio
async def test_create_audiobook_rejects_missing_folder(mock_supabase, mock_auth):
    folders_table = MagicMock()
    folders_table.select().eq().eq().execute.return_value = MagicMock(data=[])

    audiobooks_table = MagicMock()

    def table_side_effect(name):
        return {"folders": folders_table, "audiobooks": audiobooks_table}[name]

    mock_supabase.table.side_effect = table_side_effect

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/audiobooks",
            json={"title": "제목", "folder_id": "does-not-exist"},
            headers={"Authorization": "Bearer fake_token"},
        )

    assert response.status_code == 404
    audiobooks_table.insert.assert_not_called()


@pytest.mark.asyncio
async def test_delete_audiobook_success(mock_supabase, mock_auth):
    # main.py의 실제 조회 체인은 select("id").eq("id", ..).eq("user_id", ..)이다.
    # .single()을 모킹하면 이 체인과 어긋나 실제 코드는 설정 안 된(참으로 취급되는)
    # MagicMock을 받게 되어, 소유권 검증이 아예 실행되지 않아도 테스트가 통과했다.
    mock_supabase.table().select().eq().eq().execute.return_value = MagicMock(
        data=[{"id": "book1", "user_id": "test_user_id"}]  # user_id matches mocked auth!
    )

    # Mock deletion success
    mock_supabase.table().delete().eq().eq().execute.return_value = MagicMock(data=[{"id": "book1"}])
    
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.delete("/api/audiobooks/book1", headers={"Authorization": "Bearer fake_token"})
        
        assert response.status_code == 200
        assert response.json() == {"deleted": "book1"}

@pytest.mark.asyncio
async def test_delete_audiobook_forbidden(mock_supabase, mock_auth):
    # Mock supabase response indicating the book belongs to someone else!
    # In main.py, it expects a list `data=[{"id": ...}]` for select().eq().execute().data
    mock_supabase.table().select().eq().eq().execute.return_value = MagicMock(
        data=[] # Not found because user_id doesn't match
    )
    
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.delete("/api/audiobooks/book1", headers={"Authorization": "Bearer fake_token"})

        # 404 Not Found since the book doesn't belong to test_user_id (no row found matching both id and user_id)
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_audiobook_title_for_owner(mock_supabase, mock_auth):
    mock_supabase.table().update().eq().eq().execute.return_value = MagicMock(
        data=[{"id": "book1", "title": "새 제목"}]
    )

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            "/api/audiobooks/book1",
            json={"title": " 새 제목 "},
            headers={"Authorization": "Bearer fake_token"},
        )

    assert response.status_code == 200
    assert response.json() == {"id": "book1", "title": "새 제목"}


@pytest.mark.asyncio
async def test_update_audiobook_bookmark(mock_supabase, mock_auth):
    mock_supabase.table().update().eq().eq().execute.return_value = MagicMock(
        data=[{"id": "book1", "is_bookmarked": True}]
    )

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            "/api/audiobooks/book1",
            json={"is_bookmarked": True},
            headers={"Authorization": "Bearer fake_token"},
        )

    assert response.status_code == 200
    assert response.json() == {"id": "book1", "is_bookmarked": True}


@pytest.mark.asyncio
async def test_update_audiobook_folder_move_rejects_missing_folder(mock_supabase, mock_auth):
    mock_supabase.table().select().eq().eq().execute.return_value = MagicMock(data=[])

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            "/api/audiobooks/book1",
            json={"folder_id": "does-not-exist"},
            headers={"Authorization": "Bearer fake_token"},
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_audiobook_rejects_empty_payload(mock_supabase, mock_auth):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            "/api/audiobooks/book1", json={}, headers={"Authorization": "Bearer fake_token"}
        )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_save_playback_state_for_owner(mock_supabase, mock_auth):
    mock_supabase.table().upsert().execute.return_value = MagicMock(
        data=[{
            "audiobook_id": "book1",
            "current_time_seconds": 120,
            "playback_speed": 1.25,
            "repeat_mode": "all",
            "updated_at": "2026-08-01T00:00:00+00:00",
        }]
    )

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.put(
            "/api/audiobooks/book1/playback",
            json={"current_time_seconds": 120, "playback_speed": 1.25, "repeat_mode": "all"},
            headers={"Authorization": "Bearer fake_token"},
        )

    assert response.status_code == 200
    assert response.json()["current_time_seconds"] == 120
    assert response.json()["playback_speed"] == 1.25
    assert response.json()["repeat_mode"] == "all"


@pytest.mark.asyncio
async def test_get_playback_state_returns_saved_state(mock_supabase, mock_auth):
    mock_supabase.table().select().eq().eq().maybe_single().execute.return_value = MagicMock(
        data={
            "audiobook_id": "book1",
            "current_time_seconds": 120,
            "playback_speed": 1.25,
            "repeat_mode": "all",
            "updated_at": "2026-08-01T00:00:00+00:00",
        }
    )

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/audiobooks/book1/playback",
            headers={"Authorization": "Bearer fake_token"},
        )

    assert response.status_code == 200
    assert response.json()["current_time_seconds"] == 120


@pytest.mark.asyncio
async def test_get_playback_state_returns_default_when_no_history_row_exists(mock_supabase, mock_auth):
    # postgrest-py는 maybe_single()에 일치하는 행이 0개면 .execute() 자체가
    # None을 돌려준다(버전에 따른 동작). response.data로 바로 접근하면
    # AttributeError가 나서 500으로 이어졌던 회귀를 재현한다.
    mock_supabase.table().select().eq().eq().maybe_single().execute.return_value = None

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/audiobooks/book1/playback",
            headers={"Authorization": "Bearer fake_token"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "audiobook_id": "book1",
        "current_time_seconds": 0,
        "playback_speed": 1.0,
        "repeat_mode": "off",
    }


@pytest.mark.asyncio
async def test_admin_metrics_are_available_only_through_admin_route():
    metrics = {
        "total_users": 12,
        "weekly_active_users": 5,
        "week_one_retention_rate": 40,
        "generation_success_rate": 92,
    }
    with patch("routes.system.require_admin_user", return_value="admin-id"):
        with patch("routes.system.load_admin_metrics", return_value=metrics):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/api/admin/metrics", headers={"Authorization": "Bearer admin"})

    assert response.status_code == 200
    assert response.json() == metrics


@pytest.mark.asyncio
async def test_admin_metric_detail_page_is_served():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/admin/metrics/total_users")

    assert response.status_code == 200
    assert "metricPageList" in response.text


def test_admin_metrics_normalize_naive_database_timestamps_to_utc():
    from datetime import timezone
    from routes.system import _parse_event_time

    assert _parse_event_time("2026-08-01T07:00:00").tzinfo == timezone.utc
    assert _parse_event_time("2026-08-01T07:00:00+00:00").tzinfo == timezone.utc


def test_admin_metrics_include_named_users_for_detail_sheets():
    from routes.system import load_admin_metrics

    class Query:
        def __init__(self, data):
            self.data = data

        def select(self, *_):
            return self

        def gte(self, *_):
            return self

        def execute(self):
            return MagicMock(data=self.data)

    class Client:
        def table(self, name):
            return Query({
                "users": [{"id": "user-1", "full_name": "인섭", "email": "insub@example.com", "created_at": "2026-08-01T00:00:00"}],
                "audiobooks": [{"id": "book-1", "user_id": "user-1", "created_at": "2026-08-01T00:00:00"}],
                "product_events": [{"user_id": "user-1", "event_name": "playback_started", "created_at": "2026-08-01T00:00:00+00:00"}],
            }[name])

    with patch("routes.system._supabase_or_503", return_value=Client()):
        metrics = load_admin_metrics()

    assert metrics["metric_details"]["total_users"] == [{"name": "인섭", "email": "insub@example.com", "meta": "가입일 2026-08-01"}]
    assert metrics["metric_details"]["playback_started_30d"][0]["name"] == "인섭"


# ---- /api/auth/me ----
# 이전에 커버리지 0%였던 엔드포인트. 오늘 세션에서 몇 시간을 쓴
# "재로그인해도 세션이 끊기는" 버그의 클라이언트 쪽 원인이 바로 이
# 엔드포인트의 401/오류 응답을 어떻게 다루는지였는데, 정작 서버 쪽
# get_current_user 자체는 테스트가 하나도 없었다.
#
# get_current_user는 require_user_id가 아니라 직접 decode_token을 쓰므로
# mock_auth 픽스처(require_user_id 패치)로는 우회할 수 없다. 실제 JWT를
# 발급해 진짜 디코딩 경로를 태운다.

@pytest.mark.asyncio
async def test_auth_me_no_header():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/auth/me")
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_auth_me_invalid_token():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-real-jwt"})
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_auth_me_user_not_found(mock_supabase):
    from auth import create_access_token

    token = create_access_token({"sub": "ghost-user"})
    mock_supabase.table().select().eq().single().execute.return_value = MagicMock(data=None)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_auth_me_success(mock_supabase, monkeypatch):
    from auth import create_access_token

    monkeypatch.setenv("ADMIN_EMAILS", "a@b.com")
    token = create_access_token({"sub": "user-1"})
    mock_supabase.table().select().eq().single().execute.return_value = MagicMock(
        data={"id": "user-1", "email": "a@b.com", "full_name": "A", "avatar_url": None, "created_at": "2026-01-01"}
    )

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
    assert data["id"] == "user-1"
    assert data["email"] == "a@b.com"
    assert data["is_admin"] is True


@pytest.mark.asyncio
async def test_save_playback_state_truncates_fractional_seconds(mock_supabase, mock_auth):
    """실수 초를 정수로 잘라서 저장하는지 확인한다.

    ⚠️ 회귀: current_time_seconds 컬럼은 INTEGER인데 클라이언트는
    audio.currentTime을 그대로 보낸다(예: 78.63075268650299). 그대로 넘기면
    Postgres가 22P02로 거절하고, 클라이언트는 저장 실패를 조용히 무시해서
    아무도 눈치채지 못한다. 실제로 그 탓에 playback_history가 통째로 비어
    있었다 — 이어 듣기가 동작하지 않았고 관리자 대시보드의 재생 지표도 0이었다.
    기존 테스트는 전부 정수(120)만 보내서 이 문제를 잡지 못했다.
    """
    mock_supabase.table().upsert().execute.return_value = MagicMock(data=[])

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.put(
            "/api/audiobooks/book1/playback",
            json={"current_time_seconds": 78.63075268650299, "playback_speed": 1.0, "repeat_mode": "off"},
            headers={"Authorization": "Bearer fake_token"},
        )

    assert response.status_code == 200
    saved = mock_supabase.table().upsert.call_args.args[0]
    assert saved["current_time_seconds"] == 78
    assert isinstance(saved["current_time_seconds"], int)


@pytest.mark.asyncio
async def test_save_playback_state_accepts_chapter_repeat_mode(mock_supabase, mock_auth):
    """"현재 장 반복"이 서버 허용값에 있는지 확인한다.

    허용값에서 빠지면 400이 나고, 클라이언트는 저장 실패를 조용히 무시하므로
    그 모드를 켠 사용자만 이어 듣기가 조용히 망가진다.
    """
    mock_supabase.table().upsert().execute.return_value = MagicMock(data=[])

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.put(
            "/api/audiobooks/book1/playback",
            json={"current_time_seconds": 10, "playback_speed": 1.0, "repeat_mode": "chapter"},
            headers={"Authorization": "Bearer fake_token"},
        )

    assert response.status_code == 200
    assert mock_supabase.table().upsert.call_args.args[0]["repeat_mode"] == "chapter"
