"""오디오북 서명 URL 테스트.

목록에 실리는 audio_url은 응답을 만들 때 서명한 것이라 한 시간 뒤 죽는다
(SIGNED_URL_TTL). 클라이언트는 그 값을 IndexedDB에 저장해 두는데, PWA는
며칠씩 열려 있으므로 재생할 때쯤이면 이미 만료돼 있다. 경제 뉴스가 정확히
이 방식으로 404가 났었다 — 그래서 재생 직전에 한 건만 새로 발급받는다.
"""
from unittest.mock import MagicMock

import httpx
import pytest

from main import app


def _auth_headers(user_id="test_user_id"):
    from auth import create_access_token
    return {"Authorization": f"Bearer {create_access_token({'sub': user_id})}"}


@pytest.mark.asyncio
async def test_media_urls_returns_fresh_signed_urls(mock_supabase_tables):
    client, tables = mock_supabase_tables
    table = MagicMock()
    table.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": "book-1", "title": "책"},
    ]
    tables["audiobooks"] = table
    storage = MagicMock()
    storage.create_signed_url.side_effect = [
        {"signedURL": "https://storage/fresh-audio"},
        {"signedURL": "https://storage/fresh-sentences"},
    ]
    client.storage.from_.return_value = storage

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        response = await http.get("/api/audiobooks/book-1/media-urls", headers=_auth_headers())

    assert response.status_code == 200
    assert response.json() == {
        "audio_url": "https://storage/fresh-audio",
        "sentences_url": "https://storage/fresh-sentences",
    }


@pytest.mark.asyncio
async def test_media_urls_rejects_other_users_book(mock_supabase_tables):
    """⚠️ 남의 오디오북 주소를 받아 가면 안 된다. 서명 URL은 인증 없이 열리므로
    한 번 새면 그 파일이 통째로 공개된다. 조회를 user_id로 함께 거른다."""
    _client, tables = mock_supabase_tables
    table = MagicMock()
    table.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
    tables["audiobooks"] = table

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        response = await http.get("/api/audiobooks/남의-책/media-urls", headers=_auth_headers())

    assert response.status_code == 404
    # ⚠️ 404만 보면 안 된다. 목이 무조건 빈 배열을 주므로 user_id 필터를 통째로
    # 빼도 이 검사는 통과한다. 조회에 소유자 조건이 실제로 걸렸는지 확인한다.
    eq_calls = [call.args for call in table.select.return_value.eq.mock_calls if call.args]
    nested = [call.args for call in table.select.return_value.eq.return_value.eq.mock_calls if call.args]
    assert ("user_id", "test_user_id") in eq_calls + nested


@pytest.mark.asyncio
async def test_media_urls_requires_login(mock_supabase_tables):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        response = await http.get("/api/audiobooks/book-1/media-urls")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_media_urls_404_when_audio_file_missing(mock_supabase_tables):
    """업로드가 중간에 끊겨 행만 남은 경우다. audiobook_items_with_urls가
    그런 행을 조용히 건너뛰므로, 빈 목록을 200으로 넘기면 클라이언트가
    undefined를 src에 넣는다."""
    client, tables = mock_supabase_tables
    table = MagicMock()
    table.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": "book-2", "title": "오디오 없는 행"},
    ]
    tables["audiobooks"] = table
    storage = MagicMock()
    storage.create_signed_url.side_effect = RuntimeError("object not found")
    client.storage.from_.return_value = storage

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        response = await http.get("/api/audiobooks/book-2/media-urls", headers=_auth_headers())

    assert response.status_code == 404
