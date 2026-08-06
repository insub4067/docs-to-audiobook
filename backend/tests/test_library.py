"""라이브러리 /api/admin/library, /api/library* 테스트.

관리자 전용 등록 라우트라 require_admin_user를 패치해서 검증한다. 가장
중요한 불변조건: library_status가 'review'(기본값)인 작품은 공개
목록/상세에서 절대 나오면 안 된다 — 판본별 저작권이 확인되기 전까지
공개하지 않는다는 원칙 때문이다.
"""
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException

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


@pytest.fixture
def mock_supabase_tables():
    """테이블 이름별로 다른 목을 돌려주는 supabase 클라이언트.

    등록 경로는 library_jobs(작업)와 audiobooks(완성된 작품) 두 테이블을
    함께 건드린다. 위의 mock_supabase처럼 하나의 목을 공유하면 어느
    테이블에 무엇을 넣었는지 구분할 수 없어 검증이 무의미해진다.
    """
    with patch("auth.get_supabase_client") as get_client:
        client = MagicMock()
        tables: dict[str, MagicMock] = {}
        client.table.side_effect = lambda name: tables.setdefault(name, MagicMock())
        get_client.return_value = client
        yield client, tables


def _stub_pending_job(tables, *, title, content, metadata):
    """등록 직후 작업 처리기가 다시 읽어 갈 작업 행을 흉내 낸다."""
    jobs = tables.setdefault("library_jobs", MagicMock())
    jobs.select().eq().maybe_single().execute.return_value = MagicMock(data={
        "id": "job-1",
        "admin_user_id": "admin-user",
        "title": title,
        "source_text": content,
        "metadata": metadata,
    })
    return jobs


def _rows_inserted_into(tables, table_name):
    mock = tables.get(table_name)
    if mock is None:
        return []
    return [call.args[0] for call in mock.insert.call_args_list if call.args]


@pytest.mark.asyncio
async def test_add_library_rejects_non_admin():
    def reject(authorization):
        raise HTTPException(status_code=403, detail="관리자만 접근할 수 있습니다.")

    with patch("routes.library.require_admin_user", side_effect=reject):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/admin/library", json={"text": "[]"}, headers=_auth_headers())
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_add_library_rejects_malformed_json():
    with patch("routes.library.require_admin_user", return_value="admin-user"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/admin/library", json={"text": "이건 JSON이 아니다"}, headers=_auth_headers())
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_add_library_defaults_to_review_status(mock_supabase_tables):
    _client, tables = mock_supabase_tables
    _stub_pending_job(tables, title="도덕경", content="도가도 비상도", metadata={"category": "철학·사상", "status": "review"})
    payload_text = '[{"title": "도덕경", "content": "도가도 비상도", "category": "철학·사상"}]'

    with patch("routes.library.require_admin_user", return_value="admin-user"), \
         patch("routes.library.synthesize_document", side_effect=_fake_synthesize_document):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/admin/library", json={"text": payload_text}, headers=_auth_headers())

    assert response.status_code == 200
    assert response.json()["queued"] == 1

    inserted_rows = _rows_inserted_into(tables, "audiobooks")
    assert len(inserted_rows) == 1
    assert inserted_rows[0]["library_status"] == "review"
    assert inserted_rows[0]["is_library"] is True
    assert inserted_rows[0]["library_category"] == "철학·사상"


@pytest.mark.asyncio
async def test_add_library_honors_explicit_published_status(mock_supabase_tables):
    _client, tables = mock_supabase_tables
    _stub_pending_job(tables, title="논어", content="학이시습지", metadata={"status": "published"})
    payload_text = '[{"title": "논어", "content": "학이시습지", "status": "published"}]'

    with patch("routes.library.require_admin_user", return_value="admin-user"), \
         patch("routes.library.synthesize_document", side_effect=_fake_synthesize_document):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/admin/library", json={"text": payload_text}, headers=_auth_headers())

    assert response.status_code == 200
    assert _rows_inserted_into(tables, "audiobooks")[0]["library_status"] == "published"


@pytest.mark.asyncio
async def test_add_library_rejects_unknown_status_value(mock_supabase_tables):
    _client, tables = mock_supabase_tables
    # 작업 행에 이상한 status가 들어가 있어도 작품을 만들 때 다시 걸러야 한다.
    _stub_pending_job(tables, title="테스트", content="본문", metadata={"status": "definitely-verified-trust-me"})
    payload_text = '[{"title": "테스트", "content": "본문", "status": "definitely-verified-trust-me"}]'

    with patch("routes.library.require_admin_user", return_value="admin-user"), \
         patch("routes.library.synthesize_document", side_effect=_fake_synthesize_document):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/admin/library", json={"text": payload_text}, headers=_auth_headers())

    assert _rows_inserted_into(tables, "audiobooks")[0]["library_status"] == "review"


@pytest.mark.asyncio
async def test_list_all_library_items_rejects_non_admin():
    def reject(authorization):
        raise HTTPException(status_code=403, detail="관리자만 접근할 수 있습니다.")

    with patch("routes.library.require_admin_user", side_effect=reject):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/admin/library", headers=_auth_headers())
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_all_library_items_includes_review_and_published(mock_supabase):
    mock_supabase.table().select().eq().order().execute.return_value = MagicMock(data=[
        {"id": "book-1", "title": "도덕경", "library_status": "published"},
        {"id": "book-2", "title": "금강경", "library_status": "review"},
    ])

    with patch("routes.library.require_admin_user", return_value="admin-user"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/admin/library", headers=_auth_headers())

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 2
    assert {item["library_status"] for item in items} == {"published", "review"}


@pytest.mark.asyncio
async def test_update_library_status_rejects_non_admin():
    def reject(authorization):
        raise HTTPException(status_code=403, detail="관리자만 접근할 수 있습니다.")

    with patch("routes.library.require_admin_user", side_effect=reject):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.patch("/api/admin/library/book-1", json={"status": "published"}, headers=_auth_headers())
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_update_library_status_rejects_unknown_status(mock_supabase):
    with patch("routes.library.require_admin_user", return_value="admin-user"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.patch("/api/admin/library/book-1", json={"status": "definitely-verified"}, headers=_auth_headers())
    assert response.status_code == 400
    mock_supabase.table().update.assert_not_called()


@pytest.mark.asyncio
async def test_update_library_status_publishes_item(mock_supabase):
    with patch("routes.library.require_admin_user", return_value="admin-user"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.patch("/api/admin/library/book-1", json={"status": "published"}, headers=_auth_headers())

    assert response.status_code == 200
    assert response.json() == {"status": "published"}
    mock_supabase.table().update.assert_called_with({"library_status": "published"})
    eq_calls = mock_supabase.table().update().eq.call_args_list
    assert ("id", "book-1") in [c.args for c in eq_calls]


@pytest.mark.asyncio
async def test_list_library_filters_by_published_status_only(mock_supabase):
    mock_supabase.table().select().eq().eq().order().execute.return_value = MagicMock(data=[{
        "id": "book-1", "user_id": "admin-user", "title": "도덕경",
        "is_library": True, "library_status": "published",
    }])
    mock_supabase.storage.from_().create_signed_url.return_value = {"signedURL": "https://example.com/signed"}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/library")

    assert response.status_code == 200
    data = response.json()
    assert len(data["library"]) == 1

    select_calls = mock_supabase.table().select().eq.call_args_list
    assert ("is_library", True) in [c.args for c in select_calls]
    eq_on_first = mock_supabase.table().select().eq()
    assert eq_on_first.eq.call_args.args == ("library_status", "published")


@pytest.mark.asyncio
async def test_get_library_item_404s_for_review_status_item(mock_supabase):
    mock_supabase.table().select().eq().eq().eq().maybe_single().execute.return_value = MagicMock(data=None)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/library/some-review-item-id")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_saves_route_is_not_shadowed_by_audiobook_id_route():
    """/api/library/saves가 /api/library/{audiobook_id}에 잡히면 안 된다.

    FastAPI는 등록 순서대로 매칭한다. saves 라우트가 뒤에 있으면 "saves"가
    audiobook_id로 넘어가 상세 조회 핸들러가 돌고, DB에서 UUID 캐스팅에
    실패해 500이 났다 — 실제로 이 엔드포인트는 추가된 이후 프로덕션에서
    한 번도 동작하지 않았다. 로그인 없이 호출했을 때 상세 핸들러(인증
    불필요)가 아니라 saves 핸들러의 401이 나오는지로 순서를 검증한다.
    """
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/library/saves")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_library_saves_returns_empty_when_nothing_saved(mock_supabase):
    mock_supabase.table().select().eq().execute.return_value = MagicMock(data=[])

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/library/saves", headers=_auth_headers())

    assert response.status_code == 200
    assert response.json() == {"library": []}


@pytest.mark.asyncio
async def test_save_library_item_requires_login():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/library/book-1/save")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_save_library_item_rejects_unpublished_or_missing_item(mock_supabase):
    mock_supabase.table().select().eq().eq().eq().execute.return_value = MagicMock(data=[])

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/library/book-1/save", headers=_auth_headers())

    assert response.status_code == 404
    mock_supabase.table().upsert.assert_not_called()


@pytest.mark.asyncio
async def test_save_library_item_upserts_for_published_item(mock_supabase):
    mock_supabase.table().select().eq().eq().eq().execute.return_value = MagicMock(data=[{"id": "book-1"}])

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/library/book-1/save", headers=_auth_headers())

    assert response.status_code == 200
    assert response.json() == {"saved": True}
    saved = mock_supabase.table().upsert.call_args.args[0]
    assert saved["audiobook_id"] == "book-1"


@pytest.mark.asyncio
async def test_unsave_library_item():
    with patch("auth.get_supabase_client") as get_client:
        client_mock = MagicMock()
        get_client.return_value = client_mock
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.delete("/api/library/book-1/save", headers=_auth_headers())

    assert response.status_code == 200
    assert response.json() == {"saved": False}


# ── 등록 작업(library_jobs) ────────────────────────────────────────────────
# 예전에는 합성이 실패하면 audiobooks에 행이 아예 생기지 않아 서버 로그
# 말고는 아무 흔적도 남지 않았다. 무엇이 왜 실패했는지 관리자가 알 수도,
# 다시 시도할 수도 없었다. 그래서 원문을 먼저 저장한 뒤 합성한다.

@pytest.mark.asyncio
async def test_add_library_persists_source_text_before_synthesizing(mock_supabase_tables):
    _client, tables = mock_supabase_tables
    _stub_pending_job(tables, title="금강경", content="여시아문", metadata={"status": "review"})
    payload_text = '[{"title": "금강경", "content": "여시아문", "category": "종교·경전"}]'

    with patch("routes.library.require_admin_user", return_value="admin-user"), \
         patch("routes.library.synthesize_document", side_effect=_fake_synthesize_document):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/admin/library", json={"text": payload_text}, headers=_auth_headers())

    assert response.status_code == 200
    job_rows = _rows_inserted_into(tables, "library_jobs")
    assert len(job_rows) == 1
    assert job_rows[0]["source_text"] == "여시아문"
    assert job_rows[0]["title"] == "금강경"
    assert job_rows[0]["metadata"]["category"] == "종교·경전"


@pytest.mark.asyncio
async def test_failed_synthesis_records_error_instead_of_vanishing(mock_supabase_tables):
    _client, tables = mock_supabase_tables
    jobs = _stub_pending_job(tables, title="법구경", content="본문", metadata={"status": "review"})

    async def explode(*args, **kwargs):
        raise TimeoutError("TTS 요청 시간 초과")

    with patch("routes.library.require_admin_user", return_value="admin-user"), \
         patch("routes.library.synthesize_document", side_effect=explode):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/admin/library", json={"text": '[{"title": "법구경", "content": "본문"}]'}, headers=_auth_headers())

    updates = [call.args[0] for call in jobs.update.call_args_list if call.args]
    error_updates = [u for u in updates if u.get("status") == "error"]
    assert len(error_updates) == 1
    assert "TTS 요청 시간 초과" in error_updates[0]["error"]
    # 실패했으면 작품 행은 만들어지지 않아야 한다.
    assert _rows_inserted_into(tables, "audiobooks") == []
    # 그리고 원문이 담긴 작업 행은 지우면 안 된다 — 재시도의 유일한 근거다.
    jobs.delete.assert_not_called()


@pytest.mark.asyncio
async def test_successful_synthesis_removes_the_job_row(mock_supabase_tables):
    _client, tables = mock_supabase_tables
    jobs = _stub_pending_job(tables, title="도덕경", content="도가도", metadata={"status": "review"})

    with patch("routes.library.require_admin_user", return_value="admin-user"), \
         patch("routes.library.synthesize_document", side_effect=_fake_synthesize_document):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/admin/library", json={"text": '[{"title": "도덕경", "content": "도가도"}]'}, headers=_auth_headers())

    assert len(_rows_inserted_into(tables, "audiobooks")) == 1
    jobs.delete.assert_called()


@pytest.mark.asyncio
async def test_list_library_jobs_rejects_non_admin():
    def reject(authorization):
        raise HTTPException(status_code=403, detail="관리자만 접근할 수 있습니다.")

    with patch("routes.library.require_admin_user", side_effect=reject):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/admin/library/jobs", headers=_auth_headers())
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_library_jobs_returns_status_and_error(mock_supabase):
    mock_supabase.table().select().order().limit().execute.return_value = MagicMock(data=[
        {"id": "job-1", "title": "법구경", "status": "error", "error": "TimeoutError: 시간 초과"},
        {"id": "job-2", "title": "금강경", "status": "queued", "error": None},
    ])

    with patch("routes.library.require_admin_user", return_value="admin-user"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/admin/library/jobs", headers=_auth_headers())

    assert response.status_code == 200
    jobs = response.json()["jobs"]
    assert [job["status"] for job in jobs] == ["error", "queued"]
    assert "시간 초과" in jobs[0]["error"]


@pytest.mark.asyncio
async def test_list_library_jobs_does_not_return_source_text(mock_supabase):
    """작품 한 편 분량의 원문을 목록 응답에 실으면 관리자 화면이 감당하지 못한다."""
    mock_supabase.table().select().order().limit().execute.return_value = MagicMock(data=[])

    with patch("routes.library.require_admin_user", return_value="admin-user"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            await client.get("/api/admin/library/jobs", headers=_auth_headers())

    selected = mock_supabase.table().select.call_args.args[0]
    assert "source_text" not in selected


@pytest.mark.asyncio
async def test_retry_library_job_reruns_from_stored_source_text(mock_supabase_tables):
    _client, tables = mock_supabase_tables
    jobs = _stub_pending_job(tables, title="법구경", content="다시 만들 본문", metadata={"status": "review"})

    with patch("routes.library.require_admin_user", return_value="admin-user"), \
         patch("routes.library.synthesize_document", side_effect=_fake_synthesize_document):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/admin/library/jobs/job-1/retry", headers=_auth_headers())

    assert response.status_code == 200
    assert _rows_inserted_into(tables, "audiobooks")[0]["title"] == "법구경"
    jobs.delete.assert_called()


@pytest.mark.asyncio
async def test_retry_library_job_404s_for_unknown_job(mock_supabase):
    mock_supabase.table().select().eq().maybe_single().execute.return_value = MagicMock(data=None)

    with patch("routes.library.require_admin_user", return_value="admin-user"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/admin/library/jobs/nope/retry", headers=_auth_headers())

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_library_job_rejects_non_admin():
    def reject(authorization):
        raise HTTPException(status_code=403, detail="관리자만 접근할 수 있습니다.")

    with patch("routes.library.require_admin_user", side_effect=reject):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.delete("/api/admin/library/jobs/job-1", headers=_auth_headers())
    assert response.status_code == 403
