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
    # Mock supabase response for getting the book owner
    mock_supabase.table().select().eq().single().execute.return_value = MagicMock(
        data={"id": "book1", "user_id": "test_user_id"} # user_id matches mocked auth!
    )
    
    # Mock deletion success
    mock_supabase.table().delete().eq().execute.return_value = MagicMock(data=[{"id": "book1"}])
    
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
