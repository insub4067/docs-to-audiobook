"""구글 드라이브 파일 가져오기 /api/import-drive-file 테스트.

requests.get을 패치해 실제 Drive API 호출 없이 검증한다. patch 대상은
routes.import_drive다(이 모듈이 직접 부르는 이름이어야 적용된다).
"""
import pytest
import httpx
import requests
from unittest.mock import patch
from main import app


def _auth_headers():
    from auth import create_access_token
    token = create_access_token({"sub": "test_user_id"})
    return {"Authorization": f"Bearer {token}"}


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, content=b""):
        self.status_code = status_code
        self.ok = 200 <= status_code < 400
        self._json_data = json_data or {}
        self.content = content

    def json(self):
        return self._json_data


@pytest.mark.asyncio
async def test_import_drive_file_requires_auth():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/import-drive-file", json={"file_id": "f1", "access_token": "t1"})
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_import_drive_file_missing_fields():
    with patch("routes.import_drive.require_user_id", return_value="test_user_id"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/import-drive-file", json={}, headers=_auth_headers())
            assert response.status_code == 400


@pytest.mark.asyncio
async def test_import_drive_file_reports_expired_token_as_401():
    fake_meta = FakeResponse(status_code=401)
    with patch("routes.import_drive.require_user_id", return_value="test_user_id"), \
         patch("routes.import_drive.requests.get", return_value=fake_meta):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/import-drive-file", json={"file_id": "f1", "access_token": "t1"}, headers=_auth_headers()
            )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_import_drive_file_rejects_oversized_file():
    fake_meta = FakeResponse(status_code=200, json_data={
        "name": "big.txt", "mimeType": "text/plain", "size": str(999 * 1024 * 1024),
    })
    with patch("routes.import_drive.require_user_id", return_value="test_user_id"), \
         patch("routes.import_drive.requests.get", return_value=fake_meta):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/import-drive-file", json={"file_id": "f1", "access_token": "t1"}, headers=_auth_headers()
            )
    assert response.status_code == 413


@pytest.mark.asyncio
async def test_import_drive_file_rejects_unsupported_extension():
    fake_meta = FakeResponse(status_code=200, json_data={
        "name": "photo.png", "mimeType": "image/png", "size": "1024",
    })
    with patch("routes.import_drive.require_user_id", return_value="test_user_id"), \
         patch("routes.import_drive.requests.get", return_value=fake_meta):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/import-drive-file", json={"file_id": "f1", "access_token": "t1"}, headers=_auth_headers()
            )
    assert response.status_code == 400
    assert "지원하지 않는" in response.json()["detail"]


@pytest.mark.asyncio
async def test_import_drive_file_success_for_txt():
    fake_meta = FakeResponse(status_code=200, json_data={
        "name": "notes.txt", "mimeType": "text/plain", "size": "100",
    })
    fake_content = FakeResponse(status_code=200, content=("드라이브에서 가져온 충분히 긴 본문입니다. " * 10).encode("utf-8"))
    with patch("routes.import_drive.require_user_id", return_value="test_user_id"), \
         patch("routes.import_drive.requests.get", side_effect=[fake_meta, fake_content]):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/import-drive-file", json={"file_id": "f1", "access_token": "t1"}, headers=_auth_headers()
            )

    assert response.status_code == 200
    data = response.json()
    assert data["filename"] == "notes.txt"
    assert data["char_count"] > 0

    from state import text_storage
    text_storage.pop(data["text_id"], None)


@pytest.mark.asyncio
async def test_import_drive_file_exports_google_doc_as_text():
    fake_meta = FakeResponse(status_code=200, json_data={
        "name": "제안서", "mimeType": "application/vnd.google-apps.document",
    })
    fake_export = FakeResponse(status_code=200, content="구글 문서에서 내보낸 본문입니다. ".encode("utf-8") * 10)
    with patch("routes.import_drive.require_user_id", return_value="test_user_id"), \
         patch("routes.import_drive.requests.get", side_effect=[fake_meta, fake_export]):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/import-drive-file", json={"file_id": "f1", "access_token": "t1"}, headers=_auth_headers()
            )

    assert response.status_code == 200
    data = response.json()
    assert data["filename"] == "제안서"

    from state import text_storage
    text_storage.pop(data["text_id"], None)


@pytest.mark.asyncio
async def test_import_drive_file_reports_connection_failure():
    with patch("routes.import_drive.require_user_id", return_value="test_user_id"), \
         patch("routes.import_drive.requests.get", side_effect=requests.ConnectionError):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/import-drive-file", json={"file_id": "f1", "access_token": "t1"}, headers=_auth_headers()
            )
    assert response.status_code == 502
