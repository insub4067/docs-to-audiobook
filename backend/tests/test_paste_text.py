import pytest
import httpx
from main import app


@pytest.mark.asyncio
async def test_paste_text_success():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/paste-text",
            json={"text": "붙여넣은 문서 본문입니다.", "title": "내 메모"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["filename"] == "내 메모"
    assert data["char_count"] == len("붙여넣은 문서 본문입니다.")
    assert data["preview"] == "붙여넣은 문서 본문입니다."
    assert "text_id" in data
    assert "text_access_token" in data

    from state import text_storage
    text_storage.pop(data["text_id"], None)


@pytest.mark.asyncio
async def test_paste_text_rejects_empty():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/paste-text", json={"text": "   "})

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_paste_text_rejects_text_too_long():
    from state import MAX_SYNTH_CHARS

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/paste-text",
            json={"text": "가" * (MAX_SYNTH_CHARS + 1)},
        )

    assert response.status_code == 413
    assert "100,000자" in response.json()["detail"]


@pytest.mark.asyncio
async def test_paste_text_defaults_title_when_missing():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/paste-text", json={"text": "제목 없이 붙여넣기"})

    assert response.status_code == 200
    data = response.json()
    assert data["filename"] == "붙여넣은 텍스트"

    from state import text_storage
    text_storage.pop(data["text_id"], None)
