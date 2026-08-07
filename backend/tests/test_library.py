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
    payload_text = '[{"title": "도덕경", "content": "도가도 비상도", "category": "철학·사상"}]'

    with patch("routes.library.require_admin_user", return_value="admin-user"), \
         patch("routes.library.synthesize_document", side_effect=_fake_synthesize_document):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/admin/library", json={"text": payload_text}, headers=_auth_headers())

    assert response.status_code == 200
    assert response.json()["queued"] == 1

    inserted_rows = rows_inserted_into(tables, "audiobooks")
    assert len(inserted_rows) == 1
    assert inserted_rows[0]["library_status"] == "review"
    assert inserted_rows[0]["is_library"] is True
    assert inserted_rows[0]["library_category"] == "철학·사상"


@pytest.mark.asyncio
async def test_add_library_honors_explicit_published_status(mock_supabase_tables):
    _client, tables = mock_supabase_tables
    payload_text = '[{"title": "논어", "content": "학이시습지", "status": "published"}]'

    with patch("routes.library.require_admin_user", return_value="admin-user"), \
         patch("routes.library.synthesize_document", side_effect=_fake_synthesize_document):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/admin/library", json={"text": payload_text}, headers=_auth_headers())

    assert response.status_code == 200
    assert rows_inserted_into(tables, "audiobooks")[0]["library_status"] == "published"


@pytest.mark.asyncio
async def test_add_library_rejects_unknown_status_value(mock_supabase_tables):
    _client, tables = mock_supabase_tables
    # 작업 행에 이상한 status가 들어가 있어도 작품을 만들 때 다시 걸러야 한다.
    payload_text = '[{"title": "테스트", "content": "본문", "status": "definitely-verified-trust-me"}]'

    with patch("routes.library.require_admin_user", return_value="admin-user"), \
         patch("routes.library.synthesize_document", side_effect=_fake_synthesize_document):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/admin/library", json={"text": payload_text}, headers=_auth_headers())

    assert rows_inserted_into(tables, "audiobooks")[0]["library_status"] == "review"


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
    assert response.json() == {"updated": {"library_status": "published"}}
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


# ── 목록 카드 진행률 ────────────────────────────────────────────────────
# 카드마다 /api/audiobooks/{id}/playback을 부르면 작품 수만큼 요청이 나간다.
# 목록은 스크롤하며 보는 화면이라 한 번에 받아와야 한다.

@pytest.mark.asyncio
async def test_list_library_playback_requires_login():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/library/playback")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_library_playback_returns_positions_keyed_by_audiobook(mock_supabase):
    mock_supabase.table().select().eq().execute.return_value = MagicMock(data=[
        {"audiobook_id": "book-1", "current_time_seconds": 1800},
        {"audiobook_id": "book-2", "current_time_seconds": 0},
    ])

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/library/playback", headers=_auth_headers())

    assert response.status_code == 200
    assert response.json()["positions"] == {"book-1": 1800, "book-2": 0}


@pytest.mark.asyncio
async def test_list_library_playback_is_not_shadowed_by_the_id_route(mock_supabase):
    """⚠️ /api/library/{audiobook_id}가 먼저 등록되면 "playback"이 id로 잡힌다.

    library_saves가 실제로 이 함정에 걸려 추가된 이후 한 번도 동작하지
    않았다. 같은 실수를 반복하지 않도록 라우트가 살아 있는지 확인한다.
    """
    mock_supabase.table().select().eq().execute.return_value = MagicMock(data=[])

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/library/playback", headers=_auth_headers())

    # id 라우트로 새면 published 필터에 걸려 404가 난다.
    assert response.status_code == 200
    assert response.json() == {"positions": {}}


# ── 서지 정보 수정 ──────────────────────────────────────────────────────
# 제목 오타 하나 때문에 작품을 지우고 다시 등록하면 수 분짜리 재합성을
# 또 해야 한다. 본문(오디오)을 건드리지 않는 정보는 바로 고칠 수 있어야 한다.

@pytest.mark.asyncio
async def test_update_library_item_edits_bibliographic_fields(mock_supabase):
    with patch("routes.library.require_admin_user", return_value="admin-user"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.patch(
                "/api/admin/library/book-1",
                json={"title": "도덕경", "translator": "오강남", "rights": "저작권 만료"},
                headers=_auth_headers(),
            )

    assert response.status_code == 200
    mock_supabase.table().update.assert_called_with({
        "title": "도덕경",
        "library_translator": "오강남",
        "library_rights": "저작권 만료",
    })


@pytest.mark.asyncio
async def test_update_library_item_only_touches_given_fields(mock_supabase):
    """payload에 없는 필드는 건드리지 않는다 — 안 보낸 값이 지워지면 안 된다."""
    with patch("routes.library.require_admin_user", return_value="admin-user"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            await client.patch("/api/admin/library/book-1", json={"category": "철학·사상"}, headers=_auth_headers())

    assert mock_supabase.table().update.call_args.args[0] == {"library_category": "철학·사상"}


@pytest.mark.asyncio
async def test_update_library_item_clears_a_field_with_empty_string(mock_supabase):
    """빈 문자열은 "지우기"다. NULL로 넣어야 화면에서 그 줄이 사라진다."""
    with patch("routes.library.require_admin_user", return_value="admin-user"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            await client.patch("/api/admin/library/book-1", json={"edition": ""}, headers=_auth_headers())

    assert mock_supabase.table().update.call_args.args[0] == {"library_edition": None}


@pytest.mark.asyncio
async def test_update_library_item_rejects_empty_title(mock_supabase):
    with patch("routes.library.require_admin_user", return_value="admin-user"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.patch("/api/admin/library/book-1", json={"title": "  "}, headers=_auth_headers())

    assert response.status_code == 400
    mock_supabase.table().update.assert_not_called()


@pytest.mark.asyncio
async def test_update_library_item_rejects_empty_payload(mock_supabase):
    with patch("routes.library.require_admin_user", return_value="admin-user"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.patch("/api/admin/library/book-1", json={}, headers=_auth_headers())

    assert response.status_code == 400
