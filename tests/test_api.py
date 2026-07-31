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
async def test_api_synthesize_requires_auth():
    # /api/synthesize는 text_id 유무와 무관하게 인증을 먼저 확인한다.
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/synthesize", data={"text_id": "nonexistent"})
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_api_synthesize_unknown_text_id():
    # 인증은 통과했지만 text_id가 text_storage에 없으면(만료/오타) 404.
    from unittest.mock import patch
    with patch("main.require_user_id", return_value="test_user_id"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/synthesize",
                data={"text_id": "does-not-exist"},
                headers={"Authorization": "Bearer fake"},
            )
            assert response.status_code == 404
            assert "찾을 수 없거나 만료" in response.json()["detail"]


@pytest.mark.asyncio
async def test_api_synthesize_text_too_long():
    # MAX_SYNTH_CHARS를 넘는 텍스트는 413로 거절해야 한다(10MB 텍스트 =
    # 오디오만 2.9GB가 되어 인스턴스가 죽는 것을 막는 상한).
    from unittest.mock import patch
    from main import text_storage, MAX_SYNTH_CHARS

    text_storage["big"] = {
        "filename": "big.txt",
        "text": "가" * (MAX_SYNTH_CHARS + 1),
        "char_count": MAX_SYNTH_CHARS + 1,
        "created_at": 0,
    }
    with patch("main.require_user_id", return_value="test_user_id"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/synthesize",
                data={"text_id": "big"},
                headers={"Authorization": "Bearer fake"},
            )
            assert response.status_code == 413
