"""스캔본 PDF(텍스트 레이어 없음) 업로드 시 관리자 전용 Vision OCR
폴백 테스트. /api/upload가 routes.upload.detect_pdf_text_via_ocr를
부르는 지점만 패치해 검증한다."""
import io
import pytest
import httpx
from unittest.mock import patch
from fastapi import HTTPException
from main import app
from state import MAX_UPLOAD_BYTES, MAX_ADMIN_UPLOAD_BYTES


def _pdf_file(name="scanned.pdf"):
    return {"file": (name, io.BytesIO(b"%PDF-1.4 fake bytes"), "application/pdf")}


@pytest.mark.asyncio
async def test_non_admin_empty_pdf_gets_original_error_without_ocr_attempt():
    with patch("routes.upload.upload_limit_for", return_value=MAX_UPLOAD_BYTES), \
         patch("routes.upload.extract_text", return_value=""), \
         patch("routes.upload.detect_pdf_text_via_ocr") as mock_ocr:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/upload", files=_pdf_file())
    assert response.status_code == 400
    mock_ocr.assert_not_called()


@pytest.mark.asyncio
async def test_admin_empty_pdf_falls_back_to_ocr_and_succeeds():
    scanned_text = "스캔본에서 추출된 충분히 긴 본문입니다. " * 10
    with patch("routes.upload.upload_limit_for", return_value=MAX_ADMIN_UPLOAD_BYTES), \
         patch("routes.upload.extract_text", return_value=""), \
         patch("routes.upload.detect_pdf_text_via_ocr", return_value=scanned_text):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/upload", files=_pdf_file())

    assert response.status_code == 200
    data = response.json()
    assert data["char_count"] > 0

    from state import text_storage
    text_storage.pop(data["text_id"], None)


@pytest.mark.asyncio
async def test_admin_empty_pdf_ocr_also_fails_reports_original_error():
    with patch("routes.upload.upload_limit_for", return_value=MAX_ADMIN_UPLOAD_BYTES), \
         patch("routes.upload.extract_text", return_value=""), \
         patch("routes.upload.detect_pdf_text_via_ocr", side_effect=RuntimeError("vision down")):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/upload", files=_pdf_file())
    assert response.status_code == 400
    assert "추출된 텍스트가 없습니다" in response.json()["detail"]


@pytest.mark.asyncio
async def test_admin_garbled_pdf_falls_back_to_ocr_and_succeeds():
    scanned_text = "OCR로 되살린 충분히 긴 본문입니다. " * 10

    def raise_garbled(path, filename):
        raise HTTPException(status_code=400, detail="이 PDF에서 텍스트를 정상적으로 추출하지 못했습니다.")

    with patch("routes.upload.upload_limit_for", return_value=MAX_ADMIN_UPLOAD_BYTES), \
         patch("routes.upload.extract_text", side_effect=raise_garbled), \
         patch("routes.upload.detect_pdf_text_via_ocr", return_value=scanned_text):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/upload", files=_pdf_file())

    assert response.status_code == 200
    data = response.json()
    assert data["char_count"] > 0

    from state import text_storage
    text_storage.pop(data["text_id"], None)


@pytest.mark.asyncio
async def test_admin_ocr_fallback_not_attempted_for_non_pdf():
    with patch("routes.upload.upload_limit_for", return_value=MAX_ADMIN_UPLOAD_BYTES), \
         patch("routes.upload.extract_text", return_value=""), \
         patch("routes.upload.detect_pdf_text_via_ocr") as mock_ocr:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/upload",
                files={"file": ("notes.txt", io.BytesIO(b"empty source"), "text/plain")},
            )
    assert response.status_code == 400
    mock_ocr.assert_not_called()
