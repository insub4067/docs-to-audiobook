import pytest
import httpx
from main import app

@pytest.mark.asyncio
async def test_api_version():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/version")
        assert response.status_code == 200
        data = response.json()
        assert "build_id" in data

@pytest.mark.asyncio
async def test_api_voices():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/voices")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        if len(data) > 0:
            voice = data[0]
            assert "name" in voice
            assert "short_name" in voice
            assert "gender" in voice

@pytest.mark.asyncio
async def test_get_default_book_status():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/default-book")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        # It could be 'ready' or 'generating' or 'error' depending on the state
        assert data["status"] in ["ready", "generating", "error", "pending"]
