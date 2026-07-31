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
    with patch("main.require_user_id") as mock_req_user:
        mock_req_user.return_value = "test_user_id"
        yield mock_req_user

@pytest.mark.asyncio
async def test_get_audiobooks_success(mock_supabase, mock_auth):
    # Mock supabase response for selecting audiobooks
    mock_supabase.table().select().eq().order().execute.return_value = MagicMock(
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
async def test_auth_me_success(mock_supabase):
    from auth import create_access_token

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
