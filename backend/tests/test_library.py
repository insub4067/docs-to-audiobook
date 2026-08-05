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
async def test_add_library_defaults_to_review_status(mock_supabase):
    mock_supabase.table().insert().execute.return_value = MagicMock(data=[{"id": "row-1"}])
    payload_text = '[{"title": "도덕경", "content": "도가도 비상도", "category": "철학·사상"}]'

    with patch("routes.library.require_admin_user", return_value="admin-user"), \
         patch("routes.library.synthesize_document", side_effect=_fake_synthesize_document):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/admin/library", json={"text": payload_text}, headers=_auth_headers())

    assert response.status_code == 200
    assert response.json()["queued"] == 1

    insert_calls = mock_supabase.table().insert.call_args_list
    inserted_rows = [call.args[0] for call in insert_calls if call.args]
    assert len(inserted_rows) == 1
    assert inserted_rows[0]["library_status"] == "review"
    assert inserted_rows[0]["is_library"] is True
    assert inserted_rows[0]["library_category"] == "철학·사상"


@pytest.mark.asyncio
async def test_add_library_honors_explicit_published_status(mock_supabase):
    mock_supabase.table().insert().execute.return_value = MagicMock(data=[{"id": "row-1"}])
    payload_text = '[{"title": "논어", "content": "학이시습지", "status": "published"}]'

    with patch("routes.library.require_admin_user", return_value="admin-user"), \
         patch("routes.library.synthesize_document", side_effect=_fake_synthesize_document):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/admin/library", json={"text": payload_text}, headers=_auth_headers())

    assert response.status_code == 200
    inserted_rows = [call.args[0] for call in mock_supabase.table().insert.call_args_list if call.args]
    assert inserted_rows[0]["library_status"] == "published"


@pytest.mark.asyncio
async def test_add_library_rejects_unknown_status_value(mock_supabase):
    mock_supabase.table().insert().execute.return_value = MagicMock(data=[{"id": "row-1"}])
    payload_text = '[{"title": "테스트", "content": "본문", "status": "definitely-verified-trust-me"}]'

    with patch("routes.library.require_admin_user", return_value="admin-user"), \
         patch("routes.library.synthesize_document", side_effect=_fake_synthesize_document):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/admin/library", json={"text": payload_text}, headers=_auth_headers())

    inserted_rows = [call.args[0] for call in mock_supabase.table().insert.call_args_list if call.args]
    assert inserted_rows[0]["library_status"] == "review"


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
