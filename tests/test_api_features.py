import pytest
import httpx
from unittest.mock import patch, MagicMock
from main import app

@pytest.mark.asyncio
async def test_get_voice_preview():
    # Test valid preview
    with patch("main.synthesize_document") as mock_synth:
        mock_synth.return_value = (b"fake_audio", [], 0)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/voices/ko-KR-SunHiNeural/preview")
            assert response.status_code == 200
            assert response.headers["content-type"] == "audio/mpeg"
            
            # test invalid
            response = await client.get("/api/voices/invalid/preview")
            assert response.status_code == 404
            
    # Test generation failure mock
    with patch("main.os.path.exists", return_value=False):
        with patch("main.synthesize_document", side_effect=Exception("Network error")):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/api/voices/ko-KR-SunHiNeural/preview")
                assert response.status_code == 503

@pytest.mark.asyncio
async def test_social_auth_callback():
    with patch("main.SOCIAL_VERIFIERS", {"google": MagicMock(return_value={"provider_id": "g_1", "email": "a@a.com", "full_name": "A"})}):
        # We need to mock _upsert_social_user as well, which is in main.py
        with patch("main._upsert_social_user", return_value={"id": "user123", "email": "a@a.com"}):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/api/auth/social/google", json={"token": "t"})
                assert response.status_code == 200
                assert "access_token" in response.json()
            
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/auth/social/kakao", json={"token": "t"})
        assert response.status_code == 400
        
    with patch("main.SOCIAL_VERIFIERS", {"google": MagicMock(side_effect=Exception("Invalid"))}):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/auth/social/google", json={"token": "t"})
            assert response.status_code == 500

@pytest.mark.asyncio
async def test_front_end_routes():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        assert "<title>" in response.text
        
        response = await client.get("/manifest.json")
        assert response.status_code == 200
        
        response = await client.get("/sw.js")
        assert response.status_code == 200
            
@pytest.mark.asyncio
async def test_share_features():
    with patch("main.require_user_id", return_value="test_user"):
        with patch("main.save_upload_limited") as mock_save:
            mock_save.return_value = 100
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                files = {"audio": ("test.mp3", b"fake audio", "audio/mpeg")}
                data = {"title": "Test Share", "sentences": "[]", "headings": "[]"}
                response = await client.post("/api/share", data=data, files=files, headers={"Authorization": "Bearer t"})
                assert response.status_code == 200
                assert "share_id" in response.json()
                share_id = response.json()["share_id"]
                
    # Test get_share_meta
    with patch("main.os.path.exists", return_value=True):
        with patch("main.open") as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = '{"title": "Test Share", "sentences": [], "headings": []}'
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get(f"/api/share/{share_id}")
                assert response.status_code == 200
                assert response.json()["title"] == "Test Share"
                
                # Test default book meta
                with patch("main.default_book_paths", return_value=("audio", "meta")):
                    res2 = await client.get("/api/share/default_book")
                    assert res2.status_code == 200
                    assert res2.json()["title"] == "Test Share"

@pytest.mark.asyncio
async def test_serve_shared_page():
    # Test serve_shared_page
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/share/share123")
        assert response.status_code == 200
        assert "<title>" in response.text
