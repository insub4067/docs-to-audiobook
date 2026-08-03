"""이미지 텍스트 스캔 /api/scan-text 테스트.

관리자 전용 라우트라 require_admin_user를 패치해서 검증한다. Vision API
실호출은 _detect_document_text 하나로 모아뒀으므로 그 함수만 패치하면
google-cloud-vision 패키지 설치 여부와 무관하게 테스트할 수 있다.
"""
import io
import pytest
import httpx
from unittest.mock import patch
from fastapi import HTTPException
from main import app


def _auth_headers():
    from auth import create_access_token
    token = create_access_token({"sub": "test_user_id"})
    return {"Authorization": f"Bearer {token}"}


def _fake_image_file():
    return {"file": ("photo.jpg", io.BytesIO(b"fake-image-bytes"), "image/jpeg")}


@pytest.mark.asyncio
async def test_scan_text_requires_auth():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/scan-text", files=_fake_image_file())
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_scan_text_rejects_non_admin():
    def reject(authorization):
        raise HTTPException(status_code=403, detail="관리자만 접근할 수 있습니다.")

    with patch("routes.scan_text.require_admin_user", side_effect=reject):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/scan-text", files=_fake_image_file(), headers=_auth_headers())
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_scan_text_success():
    with patch("routes.scan_text.require_admin_user", return_value="admin-user"), \
         patch("routes.scan_text._detect_document_text", return_value="스캔으로 추출된 충분히 긴 본문입니다. " * 10):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/scan-text", files=_fake_image_file(), headers=_auth_headers())

    assert response.status_code == 200
    data = response.json()
    assert data["char_count"] > 0
    assert "text_id" in data

    from state import text_storage
    text_storage.pop(data["text_id"], None)


@pytest.mark.asyncio
async def test_scan_text_rejects_empty_image():
    with patch("routes.scan_text.require_admin_user", return_value="admin-user"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/scan-text",
                files={"file": ("photo.jpg", io.BytesIO(b""), "image/jpeg")},
                headers=_auth_headers(),
            )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_scan_text_reports_no_text_found():
    with patch("routes.scan_text.require_admin_user", return_value="admin-user"), \
         patch("routes.scan_text._detect_document_text", return_value=""):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/scan-text", files=_fake_image_file(), headers=_auth_headers())
    assert response.status_code == 400
    assert "찾지 못했습니다" in response.json()["detail"]


@pytest.mark.asyncio
async def test_scan_text_reports_vision_failure():
    with patch("routes.scan_text.require_admin_user", return_value="admin-user"), \
         patch("routes.scan_text._detect_document_text", side_effect=RuntimeError("permission denied")):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/scan-text", files=_fake_image_file(), headers=_auth_headers())
    assert response.status_code == 502
