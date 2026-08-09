import pytest
import httpx
from unittest.mock import patch, MagicMock
from main import app


def test_share_id_and_metadata_validation():
    from fastapi import HTTPException
    from routes.share import parse_share_metadata, validate_share_id

    assert validate_share_id("a1b2c3d4e5f6") == "a1b2c3d4e5f6"
    with pytest.raises(HTTPException, match="공유 링크"):
        validate_share_id("../default_book")
    with pytest.raises(HTTPException, match="올바른 JSON"):
        parse_share_metadata("{}", "[]")

@pytest.mark.asyncio
async def test_get_voice_preview():
    # Test valid preview
    with patch("routes.tts.synthesize_document") as mock_synth:
        mock_synth.return_value = (b"fake_audio", [], 0)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            # 신형 voice_key로도, 예전 edge-tts short_name(캐시된 구버전
            # 프론트 대응)으로도 모두 접근 가능해야 한다.
            response = await client.get("/api/voices/ko_female_calm/preview")
            assert response.status_code == 200
            assert response.headers["content-type"] == "audio/mpeg"

            response = await client.get("/api/voices/ko-KR-SunHiNeural/preview")
            assert response.status_code == 200

            # test invalid
            response = await client.get("/api/voices/invalid/preview")
            assert response.status_code == 404

    # Test generation failure mock
    with patch("routes.tts.os.path.exists", return_value=False):
        with patch("routes.tts.synthesize_document", side_effect=Exception("Network error")):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/api/voices/ko_female_calm/preview")
                assert response.status_code == 503

@pytest.mark.asyncio
async def test_social_auth_callback():
    with patch("routes.auth_social.SOCIAL_VERIFIERS", {"google": MagicMock(return_value={"provider_id": "g_1", "email": "a@a.com", "full_name": "A"})}):
        # We need to mock _upsert_social_user as well
        with patch("routes.auth_social._upsert_social_user", return_value={"id": "user123", "email": "a@a.com"}):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/api/auth/social/google", json={"token": "t"})
                assert response.status_code == 200
                assert "access_token" in response.json()
            
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/auth/social/kakao", json={"token": "t"})
        assert response.status_code == 400
        
    with patch("routes.auth_social.SOCIAL_VERIFIERS", {"google": MagicMock(side_effect=Exception("Invalid"))}):
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
    with patch("routes.share.require_user_id", return_value="test_user"):
        with patch("routes.share.save_upload_limited") as mock_save:
            mock_save.return_value = 100
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                files = {"audio": ("test.mp3", b"fake audio", "audio/mpeg")}
                data = {"title": "Test Share", "sentences": "[]", "headings": "[]"}
                response = await client.post("/api/share", data=data, files=files, headers={"Authorization": "Bearer t"})
                assert response.status_code == 200
                assert "share_id" in response.json()
                share_id = response.json()["share_id"]
                
    # Test get_share_meta
    with patch("routes.share.os.path.exists", return_value=True):
        with patch("routes.share.open") as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = '{"title": "Test Share", "sentences": [], "headings": []}'
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get(f"/api/share/{share_id}")
                assert response.status_code == 200
                assert response.json()["title"] == "Test Share"

                # Test default book meta
                with patch("routes.share.default_book_paths", return_value=("audio", "meta")):
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


async def test_config_exposes_upload_limits():
    """업로드 상한의 단일 출처. 프론트가 자체 상수를 들고 있다가 백엔드와
    어긋난 적이 있어(관리자 250MB vs 프론트 50MB), 서버가 값을 내려준다."""
    from state import MAX_UPLOAD_BYTES, MAX_ADMIN_UPLOAD_BYTES

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        body = (await client.get("/api/config")).json()

    assert body["upload_limit_bytes"] == MAX_UPLOAD_BYTES
    assert body["admin_upload_limit_bytes"] == MAX_ADMIN_UPLOAD_BYTES


def test_application_logging_defaults_to_info():
    """설정이 없으면 우리 모듈의 logger.info가 통째로 사라진다.

    uvicorn은 자기 로거만 설정하고 루트는 건드리지 않아서, 애플리케이션
    로거가 logging.lastResort(WARNING 이상)로 떨어진다. 실제로
    push_notifications의 logger.info는 한 번도 출력된 적이 없었다.

    루트 로거의 실제 상태로 검증하지 않는 이유: pytest의 logging 플러그인이
    테스트마다 루트 레벨을 자기 값으로 덮어써서, 프로덕션에서의 레벨을
    여기서 관측할 수 없다. 그래서 설정 함수의 경계에서 본다.
    """
    import main

    with patch("main.logging.basicConfig") as basic_config:
        main.configure_logging()

    assert basic_config.call_args.kwargs["level"] == "INFO"


def test_log_level_can_be_overridden_by_env():
    import os as _os
    import main

    with patch.dict(_os.environ, {"LOG_LEVEL": "WARNING"}), \
         patch("main.logging.basicConfig") as basic_config:
        main.configure_logging()

    assert basic_config.call_args.kwargs["level"] == "WARNING"


async def test_startup_uses_lifespan_not_deprecated_event():
    """@app.on_event("startup")은 FastAPI에서 deprecated다. lifespan으로
    옮기면서 부팅 준비 작업이 실제로 도는지 함께 고정한다."""
    from unittest.mock import patch as _patch

    with _patch("routes.tts.resume_background_synthesis_jobs") as resume, \
         _patch("routes.default_book.prepare_default_book_from_cache") as prepare, \
         _patch("cleanup.cleanup_expired_files_loop") as cleanup_loop:
        async def _noop():
            return None
        resume.side_effect = lambda: _noop()
        prepare.side_effect = lambda: _noop()
        cleanup_loop.side_effect = lambda: _noop()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.get("/api/version")

    assert app.router.on_startup == []
