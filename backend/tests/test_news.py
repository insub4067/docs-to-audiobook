"""오늘의 뉴스 /api/admin/news, /api/news 테스트.

관리자 전용 등록 라우트라 require_admin_user를 패치해서 검증한다. 실제
TTS 호출은 synthesize_document 하나로 모아 패치해 edge-tts/구글 TTS
실호출 없이 테스트한다.
"""
import json
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
async def test_add_news_replaces_all_previous_news(mock_supabase_tables):
    """새 묶음이 성공하면 이전 뉴스를 행·Storage까지 통째로 지운다.

    경제 뉴스는 매일 갈리는 피드라 지난 것을 남겨 둘 이유가 없다. 남겨 두니
    같은 기사가 두 번씩 든 목록이 만들어졌다(등록을 두 번 눌러서 생긴 일이다).
    """
    client_mock, _tables = mock_supabase_tables
    audiobooks = client_mock.table("audiobooks")
    audiobooks.select().eq().execute.return_value = MagicMock(data=[
        {"id": "old-1", "user_id": "admin-user"},
        {"id": "old-2", "user_id": "other-admin"},
    ])
    # ⚠️ 10개 제한 정리가 대신 지워 주면 교체 로직이 없어도 테스트가 통과한다
    # (실제로 뮤테이션에서 그렇게 샜다). 두 행 모두 "최신 10개 안"이라고 둬서,
    # 지워진다면 그건 오직 교체 때문이게 만든다.
    audiobooks.select().eq().order().limit().execute.return_value = MagicMock(
        data=[{"id": "old-1"}, {"id": "old-2"}]
    )

    with patch("routes.news.require_admin_user", return_value="admin-user"), \
         patch("routes.news.synthesize_document", side_effect=_fake_synthesize_document):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/admin/news",
                json={"text": '[{"title": "새 뉴스", "content": "본문"}]'},
                headers=_auth_headers(),
            )

    assert response.status_code == 200
    assert response.json()["replacing"] == 2

    deleted_ids = [call.args for call in audiobooks.delete().eq.call_args_list]
    assert ("id", "old-1") in deleted_ids
    assert ("id", "old-2") in deleted_ids

    # 행만 지우면 화면에서만 사라지고 버킷은 계속 불어난다.
    removed_paths = [call.args[0] for call in client_mock.storage.from_().remove.call_args_list]
    assert ["admin-user/old-1.mp3", "admin-user/old-1.sentences.json"] in removed_paths
    assert ["other-admin/old-2.mp3", "other-admin/old-2.sentences.json"] in removed_paths


@pytest.mark.asyncio
async def test_add_news_keeps_previous_news_when_every_item_fails(mock_supabase_tables):
    """⚠️ 합성이 통째로 실패하면 이전 뉴스를 지우지 않는다.

    등록을 받자마자 지우면 실패했을 때 화면에 아무것도 남지 않는다.
    새 뉴스가 없는 것보다 어제 뉴스라도 있는 게 낫다."""
    client_mock, _tables = mock_supabase_tables
    audiobooks = client_mock.table("audiobooks")
    audiobooks.select().eq().execute.return_value = MagicMock(data=[
        {"id": "old-1", "user_id": "admin-user"},
    ])
    audiobooks.select().eq().order().limit().execute.return_value = MagicMock(
        data=[{"id": "old-1"}]
    )

    async def always_fails(*args, **kwargs):
        raise RuntimeError("합성 실패")

    with patch("routes.news.require_admin_user", return_value="admin-user"), \
         patch("routes.news.synthesize_document", side_effect=always_fails):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/admin/news",
                json={"text": '[{"title": "새 뉴스", "content": "본문"}]'},
                headers=_auth_headers(),
            )

    assert response.status_code == 200
    deleted_ids = [call.args for call in audiobooks.delete().eq.call_args_list]
    assert ("id", "old-1") not in deleted_ids


@pytest.mark.asyncio
async def test_add_news_keeps_at_most_ten_rows_in_db(mock_supabase_tables):
    """DB에 뉴스는 항상 최신 10개까지만 남는다(마지막 방어선)."""
    client_mock, _tables = mock_supabase_tables
    audiobooks = client_mock.table("audiobooks")
    keep = [{"id": f"keep-{i}"} for i in range(10)]
    audiobooks.select().eq().order().limit().execute.return_value = MagicMock(data=keep)
    audiobooks.select().eq().execute.return_value = MagicMock(data=[
        *[{"id": row["id"], "user_id": "admin-user"} for row in keep],
        {"id": "extra-1", "user_id": "admin-user"},
        {"id": "extra-2", "user_id": "admin-user"},
    ])

    with patch("routes.news.require_admin_user", return_value="admin-user"), \
         patch("routes.news.synthesize_document", side_effect=_fake_synthesize_document):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            await client.post(
                "/api/admin/news",
                json={"text": '[{"title": "새 뉴스", "content": "본문"}]'},
                headers=_auth_headers(),
            )

    deleted_ids = [call.args for call in audiobooks.delete().eq.call_args_list]
    assert ("id", "extra-1") in deleted_ids
    assert ("id", "extra-2") in deleted_ids


@pytest.mark.asyncio
async def test_add_news_drops_duplicate_titles_within_one_batch(mock_supabase_tables):
    """같은 붙여넣기 안에 같은 기사가 두 번 들어오면 하나만 등록한다."""
    _client_mock, tables = mock_supabase_tables

    payload = json.dumps([
        {"title": "달러 약세", "content": "본문 A"},
        {"title": "  달러   약세  ", "content": "본문 B"},
        {"title": "금값 급등", "content": "본문 C"},
    ], ensure_ascii=False)

    with patch("routes.news.require_admin_user", return_value="admin-user"), \
         patch("routes.news.synthesize_document", side_effect=_fake_synthesize_document):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/admin/news", json={"text": payload}, headers=_auth_headers()
            )

    assert response.json()["queued"] == 2
    titles = [row["title"] for row in rows_inserted_into(tables, "content_jobs")]
    assert titles == ["달러 약세", "금값 급등"]


@pytest.mark.asyncio
async def test_add_news_rejects_while_another_batch_is_processing(mock_supabase_tables):
    """⚠️ 실수로 두 번 누르면 두 묶음이 겹친다.

    두 번째 요청이 캡처한 "이전 목록"에는 첫 번째 결과가 아직 없어서, 나중에
    이전 것을 지울 때 첫 번째 묶음만 살아남는다. 그렇게 같은 기사가 두 번씩
    든 목록이 실제로 만들어졌다."""
    _client_mock, tables = mock_supabase_tables
    jobs_table = tables["content_jobs"]
    jobs_table.insert({"id": "running-job", "kind": "news", "title": "처리 중"})
    jobs_table.rows["running-job"]["status"] = "processing"

    with patch("routes.news.require_admin_user", return_value="admin-user"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/admin/news",
                json={"text": '[{"title": "새 뉴스", "content": "본문"}]'},
                headers=_auth_headers(),
            )

    assert response.status_code == 429


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


@pytest.mark.asyncio
async def test_list_news_hides_duplicate_rows_already_in_db(mock_supabase_tables):
    """⚠️ 등록 단계에서 거르기 전에 들어간 중복 행이 DB에 남아 있다.

    실제로 붙여넣은 JSON에 같은 기사가 두 번씩 든 적이 있었고, 그 10행이
    그대로 남아 재생목록과 "연속 듣기"에서 같은 기사가 두 번 재생됐다.
    데이터를 건드리지 않고도 화면에는 한 번만 나와야 한다."""
    client_mock, _tables = mock_supabase_tables
    audiobooks = client_mock.table("audiobooks")
    audiobooks.select().eq().gte().order().limit().execute.return_value = MagicMock(data=[
        {"id": "new", "user_id": "admin", "title": "금값 급등"},
        {"id": "old", "user_id": "admin", "title": "  금값   급등 "},
        {"id": "other", "user_id": "admin", "title": "중국 수출"},
    ])

    def fake_items(_supabase, _user_id, rows):
        return [{"id": row["id"], "title": row["title"]} for row in rows]

    with patch("routes.news.audiobook_items_with_urls", side_effect=fake_items):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/news")

    ids = [item["id"] for item in response.json()["news"]]
    # 최신순으로 오므로 더 최근인 "new"가 남는다.
    assert ids == ["new", "other"]
