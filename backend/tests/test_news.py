"""오늘의 뉴스 /api/admin/news, /api/news 테스트.

관리자 전용 등록 라우트라 require_admin_user를 패치해서 검증한다. 실제
TTS 호출은 synthesize_document 하나로 모아 패치해 edge-tts/구글 TTS
실호출 없이 테스트한다.
"""
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException

from tests.conftest import rows_inserted_into
from main import app


def _auth_headers():
    from auth import create_access_token
    token = create_access_token({"sub": "test_user_id"})
    return {"Authorization": f"Bearer {token}"}


async def _fake_synthesize_document(text, voice, rate, pitch, progress_callback=None, provider_name=None):
    return b"fake-mp3-bytes", [{"text": text, "start": 0, "end": 1000}], []


@pytest.fixture
def mock_supabase():
    with patch("auth.get_supabase_client") as get_client:
        client = MagicMock()
        get_client.return_value = client
        yield client


@pytest.mark.asyncio
async def test_add_news_rejects_non_admin():
    def reject(authorization):
        raise HTTPException(status_code=403, detail="관리자만 접근할 수 있습니다.")

    with patch("routes.news.require_admin_user", side_effect=reject):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/admin/news", json={"text": "[]"}, headers=_auth_headers())
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_add_news_rejects_malformed_json():
    with patch("routes.news.require_admin_user", return_value="admin-user"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/admin/news", json={"text": "이건 JSON이 아니다"}, headers=_auth_headers())
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_add_news_rejects_empty_array():
    with patch("routes.news.require_admin_user", return_value="admin-user"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/admin/news", json={"text": "[]"}, headers=_auth_headers())
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_add_news_strips_json_code_fence_and_stores_items(mock_supabase_tables):
    _client, tables = mock_supabase_tables
    payload_text = (
        "```json\n"
        '[{"title": "첫 뉴스", "content": "첫 뉴스 본문입니다.", "category": "국제", "source": "Reuters"},'
        ' {"title": "둘째 뉴스", "content": "둘째 뉴스 본문입니다."}]'
        "\n```"
    )

    with patch("routes.news.require_admin_user", return_value="admin-user"), \
         patch("routes.news.synthesize_document", side_effect=_fake_synthesize_document):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/admin/news", json={"text": payload_text}, headers=_auth_headers())

    assert response.status_code == 200
    data = response.json()
    assert data["queued"] == 2

    inserted_rows = rows_inserted_into(tables, "audiobooks")
    assert all(row["is_news"] is True for row in inserted_rows)
    assert all(row["user_id"] == "admin-user" for row in inserted_rows)
    assert inserted_rows[0]["news_category"] == "국제"
    assert inserted_rows[0]["news_source"] == "Reuters"
    assert inserted_rows[1]["news_category"] is None
    assert all(row["duration_seconds"] == 1 for row in inserted_rows)


@pytest.mark.asyncio
async def test_add_news_strips_chatgpt_citation_markers_from_content(mock_supabase_tables):
    payload_text = (
        '[{"title": "산불 뉴스", '
        '"content": "건물 700여 채가 파괴됐습니다.  [oaicitation:8\\u2021Reuters]."}]'
    )

    captured_text = {}

    async def capturing_synthesize(text, voice, rate, pitch, progress_callback=None, provider_name=None):
        captured_text["content"] = text
        return await _fake_synthesize_document(text, voice, rate, pitch)

    with patch("routes.news.require_admin_user", return_value="admin-user"), \
         patch("routes.news.synthesize_document", side_effect=capturing_synthesize):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/admin/news", json={"text": payload_text}, headers=_auth_headers())

    assert response.status_code == 200
    assert "oaicitation" not in captured_text["content"]
    assert captured_text["content"] == "건물 700여 채가 파괴됐습니다."


@pytest.mark.asyncio
async def test_add_news_skips_items_missing_title_or_content(mock_supabase_tables):
    _client, tables = mock_supabase_tables
    payload_text = '[{"title": "제목만 있음"}, {"title": "정상 뉴스", "content": "본문 내용"}]'

    with patch("routes.news.require_admin_user", return_value="admin-user"), \
         patch("routes.news.synthesize_document", side_effect=_fake_synthesize_document):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/admin/news", json={"text": payload_text}, headers=_auth_headers())

    assert response.status_code == 200
    data = response.json()
    assert data["queued"] == 1

    inserted_rows = rows_inserted_into(tables, "audiobooks")
    assert len(inserted_rows) == 1
    assert inserted_rows[0]["title"] == "정상 뉴스"


@pytest.mark.asyncio
async def test_add_news_reports_partial_failure_without_failing_whole_request(mock_supabase_tables):
    _client, tables = mock_supabase_tables
    payload_text = '[{"title": "실패할 뉴스", "content": "본문"}, {"title": "성공할 뉴스", "content": "본문"}]'

    calls = {"n": 0}

    async def flaky_synthesize(text, voice, rate, pitch, progress_callback=None, provider_name=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("합성 실패")
        return await _fake_synthesize_document(text, voice, rate, pitch)

    with patch("routes.news.require_admin_user", return_value="admin-user"), \
         patch("routes.news.synthesize_document", side_effect=flaky_synthesize):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/admin/news", json={"text": payload_text}, headers=_auth_headers())

    assert response.status_code == 200
    data = response.json()
    assert data["queued"] == 2

    inserted_rows = rows_inserted_into(tables, "audiobooks")
    assert len(inserted_rows) == 1
    assert inserted_rows[0]["title"] == "성공할 뉴스"


@pytest.mark.asyncio
async def test_add_news_broadcasts_push_after_background_processing(mock_supabase_tables):
    payload_text = '[{"title": "첫 뉴스", "content": "본문1"}, {"title": "둘째 뉴스", "content": "본문2"}]'

    with patch("routes.news.require_admin_user", return_value="admin-user"), \
         patch("routes.news.synthesize_document", side_effect=_fake_synthesize_document), \
         patch("routes.news.send_news_ready_broadcast") as broadcast:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/admin/news", json={"text": payload_text}, headers=_auth_headers())

    assert response.status_code == 200
    broadcast.assert_called_once_with(2)


@pytest.mark.asyncio
async def test_add_news_skips_broadcast_when_nothing_created(mock_supabase_tables):
    payload_text = '[{"title": "실패할 뉴스", "content": "본문"}]'

    async def always_fails(text, voice, rate, pitch, progress_callback=None, provider_name=None):
        raise RuntimeError("합성 실패")

    with patch("routes.news.require_admin_user", return_value="admin-user"), \
         patch("routes.news.synthesize_document", side_effect=always_fails), \
         patch("routes.news.send_news_ready_broadcast") as broadcast:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/admin/news", json={"text": payload_text}, headers=_auth_headers())

    assert response.status_code == 200
    broadcast.assert_not_called()


@pytest.mark.asyncio
async def test_add_news_deletes_rows_and_storage_that_fell_outside_visible_window(mock_supabase_tables):
    """새 뉴스를 등록하면, 공개 목록(list_news)에서 이미 벗어난(3일 초과
    또는 최신 10개 밖으로 밀려난) 오래된 뉴스가 DB 행 + Storage 음성
    파일까지 함께 삭제되는지 확인한다. 화면에 안 보인다고 실제로 지워지는
    건 아니었던 문제를 고친 것이라, 두 종류(스토리지/행) 모두 지워지는
    것을 각각 확인해야 한다."""
    client_mock, _tables = mock_supabase_tables
    audiobooks = client_mock.table("audiobooks")
    # list_news와 정확히 같은 쿼리(select→eq→gte→order→limit)로 "보이는" 것만 반환.
    audiobooks.select().eq().gte().order().limit().execute.return_value = MagicMock(
        data=[{"id": "visible-1"}, {"id": "visible-2"}]
    )
    # 정리 대상을 고르기 위한 전체 목록(select→eq)에는 보이는 것 + 밀려난 것이 섞여 있다.
    audiobooks.select().eq().execute.return_value = MagicMock(data=[
        {"id": "visible-1", "user_id": "admin-user"},
        {"id": "visible-2", "user_id": "admin-user"},
        {"id": "stale-1", "user_id": "admin-user"},
        {"id": "stale-2", "user_id": "other-admin"},
    ])

    with patch("routes.news.require_admin_user", return_value="admin-user"), \
         patch("routes.news.synthesize_document", side_effect=_fake_synthesize_document):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/admin/news",
                json={"text": '[{"title": "새 뉴스", "content": "본문"}]'},
                headers=_auth_headers(),
            )

    assert response.status_code == 200

    deleted_ids = [call.args for call in audiobooks.delete().eq.call_args_list]
    assert ("id", "stale-1") in deleted_ids
    assert ("id", "stale-2") in deleted_ids
    assert ("id", "visible-1") not in deleted_ids
    assert ("id", "visible-2") not in deleted_ids

    removed_paths = [call.args[0] for call in client_mock.storage.from_().remove.call_args_list]
    assert ["admin-user/stale-1.mp3", "admin-user/stale-1.sentences.json"] in removed_paths
    assert ["other-admin/stale-2.mp3", "other-admin/stale-2.sentences.json"] in removed_paths


@pytest.mark.asyncio
async def test_add_news_cleanup_runs_even_when_every_item_fails(mock_supabase_tables):
    """등록이 전부 실패해도(합성 에러 등) 오래된 뉴스 정리는 별개로 돈다."""
    client_mock, _tables = mock_supabase_tables
    audiobooks = client_mock.table("audiobooks")
    audiobooks.select().eq().gte().order().limit().execute.return_value = MagicMock(data=[])
    audiobooks.select().eq().execute.return_value = MagicMock(
        data=[{"id": "stale-1", "user_id": "admin-user"}]
    )

    async def always_fails(text, voice, rate, pitch, progress_callback=None, provider_name=None):
        raise RuntimeError("합성 실패")

    with patch("routes.news.require_admin_user", return_value="admin-user"), \
         patch("routes.news.synthesize_document", side_effect=always_fails):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/admin/news",
                json={"text": '[{"title": "실패할 뉴스", "content": "본문"}]'},
                headers=_auth_headers(),
            )

    assert response.status_code == 200
    deleted_ids = [call.args for call in audiobooks.delete().eq.call_args_list]
    assert ("id", "stale-1") in deleted_ids


@pytest.mark.asyncio
async def test_list_news_filters_recent_news_items_only(mock_supabase):
    rows = [{
        "id": "news-1", "user_id": "admin-user", "title": "오늘 뉴스",
        "is_news": True, "news_category": "경제", "news_source": "Bloomberg",
        "created_at": "2026-08-05T00:00:00+00:00",
    }]
    mock_supabase.table().select().eq().gte().order().limit().execute.return_value = MagicMock(data=rows)
    mock_supabase.storage.from_().create_signed_url.return_value = {"signedURL": "https://example.com/signed"}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/news")

    assert response.status_code == 200
    data = response.json()
    assert len(data["news"]) == 1
    assert data["news"][0]["title"] == "오늘 뉴스"
    assert data["news"][0]["audio_url"] == "https://example.com/signed"

    select_call = mock_supabase.table().select().eq.call_args
    assert select_call.args == ("is_news", True)
