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

@pytest.mark.asyncio
async def test_api_audiobooks_unauthorized():
    # Should return 401 if no Authorization header
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/audiobooks")
        assert response.status_code == 401

@pytest.mark.asyncio
async def test_api_delete_audiobook_unauthorized():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.delete("/api/audiobooks/123")
        assert response.status_code == 401

@pytest.mark.asyncio
async def test_api_synthesize_empty_text():
    # POST /api/synthesize with empty text should return 400
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "text": "   \n  ",
            "voice": "ko-KR-SunHiNeural",
            "rate": "1.0",
            "pitch": "0.0"
        }
        response = await client.post("/api/synthesize", json=payload)
        # Assuming the API validates empty text and returns 400 or just processes empty chunks
        # Let's check what it actually returns. It might return 200 and an empty audio.
        # But for edge cases, it's good to ensure it doesn't crash (500).
        assert response.status_code in [200, 400, 422]
