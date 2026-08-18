"""라이브러리 /api/admin/library, /api/library* 테스트.

관리자 전용 등록 라우트라 require_admin_user를 패치해서 검증한다. 가장
중요한 불변조건: library_status가 'review'(기본값)인 작품은 공개
목록/상세에서 절대 나오면 안 된다 — 판본별 저작권이 확인되기 전까지
공개하지 않는다는 원칙 때문이다.
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


# 뉴스·라이브러리는 디스크 경유 경로로 합성한다(메모리에 MP3 전체를 들고
# 있지 않기 위해서). 가짜도 output_path에 파일을 써야 한다.
async def _fake_synthesize_document(text, voice, rate, pitch, output_path, progress_callback=None, **kwargs):
    with open(output_path, "wb") as audio_file:
        audio_file.write(b"fake-mp3-bytes")
    return [{"text": text, "start": 0, "end": 1000}], [], ""


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
         patch("routes.tts.synthesize_document_to_file", side_effect=_fake_synthesize_document):
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
         patch("routes.tts.synthesize_document_to_file", side_effect=_fake_synthesize_document):
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
         patch("routes.tts.synthesize_document_to_file", side_effect=_fake_synthesize_document):
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
    mock_supabase.table().select().eq().is_().order().execute.return_value = MagicMock(data=[
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
    mock_supabase.table().select().eq().eq().is_().order().execute.return_value = MagicMock(data=[{
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
    # 작품 행을 먼저 고치고, 그다음 부에 제목을 전파한다. 그래서 마지막
    # 호출이 아니라 첫 호출을 본다.
    updates = [call.args[0] for call in mock_supabase.table().update.call_args_list]
    assert updates[0] == {
        "title": "도덕경",
        "library_translator": "오강남",
        "library_rights": "저작권 만료",
    }
    # 서지 정보 중 부에 밀어 넣는 것은 제목뿐이다 — 역자·권리는 작품 행에만 둔다.
    assert updates[1] == {"title": "도덕경"}


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


def test_library_payload_rejects_too_many_items_at_once():
    """긴 경전 수십 편이 한 번에 들어오면 합성이 몇 시간 이어지고, 그동안
    공유 CPU 하나를 물고 있어 일반 사용자 변환까지 굶는다."""
    from routes.library import _parse_library_payload, MAX_LIBRARY_PARTS_PER_REQUEST

    too_many = json.dumps([
        {"title": f"작품 {i}", "content": "본문"}
        for i in range(MAX_LIBRARY_PARTS_PER_REQUEST + 1)
    ])

    with pytest.raises(HTTPException) as exc:
        _parse_library_payload(too_many)
    assert exc.value.status_code == 413


def test_library_payload_rejects_a_single_oversized_work():
    from state import MAX_ADMIN_SYNTH_CHARS
    from routes.library import _parse_library_payload

    huge = json.dumps([{"title": "너무 긴 경전", "content": "가" * (MAX_ADMIN_SYNTH_CHARS + 1)}])

    with pytest.raises(HTTPException) as exc:
        _parse_library_payload(huge)
    assert exc.value.status_code == 413


def test_library_payload_accepts_a_normal_batch():
    """상한이 정상 등록을 막으면 안 된다."""
    from routes.library import _parse_library_payload, MAX_LIBRARY_PARTS_PER_REQUEST

    normal = json.dumps([
        {"title": f"작품 {i}", "content": "본문입니다."}
        for i in range(MAX_LIBRARY_PARTS_PER_REQUEST)
    ])

    assert len(_parse_library_payload(normal)) == MAX_LIBRARY_PARTS_PER_REQUEST


# ── 시리즈(부로 나뉜 작품) ──────────────────────────────────────────────
# 오디세이처럼 긴 작품은 부 여러 개로 나눠 등록한다. 서점 목록에는 작품
# 하나로만 보이고, 상세에서 부가 재생목록이 된다.

def test_library_payload_reads_parts_as_a_series():
    from routes.library import _parse_library_payload

    payload = json.dumps([{
        "title": "오디세이",
        "category": "고전문학",
        "parts": [
            {"title": "제1권", "content": "첫 번째 본문"},
            {"title": "제2권", "content": "두 번째 본문"},
        ],
    }])

    works = _parse_library_payload(payload)
    assert len(works) == 1
    assert [part["title"] for part in works[0]["parts"]] == ["제1권", "제2권"]
    assert works[0]["category"] == "고전문학"


def test_library_payload_still_reads_a_single_work_without_parts():
    """parts가 없는 예전 형식은 그대로 동작해야 한다 — 이미 등록된 8편이
    쓰던 형식이고, 관리자가 짧은 작품을 올릴 때도 계속 이 형식을 쓴다."""
    from routes.library import _parse_library_payload

    works = _parse_library_payload(json.dumps([{"title": "도덕경", "content": "도가도 비상도"}]))

    assert len(works) == 1
    # 단권도 "부가 하나인 작품"으로 펴서 저장 경로가 갈리지 않게 한다.
    # 부 제목이 None인 것이 단권의 표지다.
    assert works[0]["parts"] == [{"title": None, "content": "도가도 비상도"}]


def test_library_payload_counts_parts_not_works_against_the_limit():
    """상한은 작품이 아니라 부로 센다. 24권짜리 하나는 작품 수로는 1이지만
    합성은 24번 돌아 CPU를 그만큼 오래 물고 있다."""
    from routes.library import _parse_library_payload, MAX_LIBRARY_PARTS_PER_REQUEST

    too_many_parts = json.dumps([{
        "title": "너무 긴 서사시",
        "parts": [
            {"title": f"제{i}권", "content": "본문"}
            for i in range(MAX_LIBRARY_PARTS_PER_REQUEST + 1)
        ],
    }])

    with pytest.raises(HTTPException) as exc:
        _parse_library_payload(too_many_parts)
    assert exc.value.status_code == 413


def test_expand_assigns_ids_up_front_so_parts_can_point_at_part_one():
    """부의 id를 저장 시점이 아니라 큐잉 시점에 확정한다.

    2부는 자기가 어느 작품에 속하는지 적어야 하는데 그 값이 1부의 id다.
    저장할 때 uuid를 만들면 2부가 그 값을 미리 알 방법이 없다.
    """
    from routes.library import _parse_library_payload, _expand_to_job_items

    works = _parse_library_payload(json.dumps([{
        "title": "오디세이",
        "parts": [
            {"title": "제1권", "content": "본문 1"},
            {"title": "제2권", "content": "본문 2"},
            {"title": "제3권", "content": "본문 3"},
        ],
    }]))
    items = _expand_to_job_items(works)

    assert len(items) == 3
    work_id = items[0]["audiobook_id"]
    # 1부가 작품 대표 행이다 — part_of가 비어 있어야 목록 쿼리에 잡힌다.
    assert items[0]["part_of"] is None
    assert [item["part_of"] for item in items[1:]] == [work_id, work_id]
    assert [item["part_number"] for item in items] == [1, 2, 3]
    assert [item["part_title"] for item in items] == ["제1권", "제2권", "제3권"]
    # 부마다 id가 달라야 한다. 같으면 뒤 부가 앞 부를 덮어쓴다.
    assert len({item["audiobook_id"] for item in items}) == 3


def test_expand_keeps_a_single_work_free_of_part_columns():
    """단권은 세 컬럼이 전부 NULL이라 기존 8편과 완전히 같은 모양이 된다."""
    from routes.library import _parse_library_payload, _expand_to_job_items

    works = _parse_library_payload(json.dumps([{"title": "도덕경", "content": "도가도 비상도"}]))
    item = _expand_to_job_items(works)[0]

    assert item["part_of"] is None
    assert item["part_number"] is None
    assert item["part_title"] is None
    assert item["title"] == "도덕경"


def test_expand_labels_jobs_with_part_position_for_the_admin_list():
    """24부를 등록하면 관리 화면의 등록 작업 목록에 같은 제목이 24줄
    늘어선다. 어디서 멈췄는지 보이도록 몇 번째 부인지까지 적는다."""
    from routes.library import _parse_library_payload, _expand_to_job_items

    works = _parse_library_payload(json.dumps([{
        "title": "오디세이",
        "parts": [{"title": "제1권 · 아테나의 방문", "content": "본문 1"},
                  {"title": "제2권 · 텔레마코스의 출항", "content": "본문 2"}],
    }]))
    items = _expand_to_job_items(works)

    assert items[1]["title"] == "오디세이 · 2/2 제2권 · 텔레마코스의 출항"
    # 오디오북 행에 들어갈 진짜 제목은 따로 넘긴다 — 작업 라벨이 작품명을
    # 덮어쓰면 서점 카드에 "오디세이 · 2/2"가 뜬다.
    assert items[1]["work_title"] == "오디세이"


@pytest.mark.asyncio
async def test_add_library_series_stores_every_part_linked_to_part_one(mock_supabase_tables):
    _client, tables = mock_supabase_tables
    payload_text = json.dumps([{
        "title": "오디세이",
        "status": "published",
        "parts": [
            {"title": "제1권", "content": "본문 1"},
            {"title": "제2권", "content": "본문 2"},
        ],
    }])

    with patch("routes.library.require_admin_user", return_value="admin-user"), \
         patch("routes.tts.synthesize_document_to_file", side_effect=_fake_synthesize_document):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/admin/library", json={"text": payload_text}, headers=_auth_headers())

    assert response.status_code == 200
    assert response.json() == {"queued": 2, "works": 1}

    rows = rows_inserted_into(tables, "audiobooks")
    assert len(rows) == 2
    first, second = rows
    # 두 행 모두 작품명을 제목으로 갖는다. 부 제목은 따로 있다.
    assert first["title"] == second["title"] == "오디세이"
    assert [row["library_part_title"] for row in rows] == ["제1권", "제2권"]
    assert first["library_part_of"] is None
    assert second["library_part_of"] == first["id"]
    assert [row["library_part_number"] for row in rows] == [1, 2]
    # 부에도 같은 공개 상태가 들어가야 한다. 작품만 published면 목록에는
    # 보이는데 2부부터 재생이 안 되는 작품이 만들어진다.
    assert {row["library_status"] for row in rows} == {"published"}


@pytest.mark.asyncio
async def test_retrying_a_failed_part_reuses_the_same_audiobook_id(mock_supabase_tables):
    """실패한 부를 재시도하면 같은 id로 행이 되살아나, 이미 만들어져 있던
    나머지 부가 그대로 붙는다. 1부가 실패해 작품이 통째로 안 보이던
    상태도 재시도 한 번으로 복구된다.

    id를 저장 시점에 만들었다면 재시도마다 새 id가 생겨, 나머지 부들이
    영영 존재하지 않는 작품을 가리켰을 것이다.
    """
    from routes.library import store_library_item

    _client, tables = mock_supabase_tables
    fixed_id = "11111111-2222-3333-4444-555555555555"
    item = {
        "title": "오디세이 · 1/2 제1권",
        "work_title": "오디세이",
        "content": "본문 1",
        "audiobook_id": fixed_id,
        "part_of": None,
        "part_number": 1,
        "part_title": "제1권",
        "status": "published",
    }

    with patch("routes.tts.synthesize_document_to_file", side_effect=_fake_synthesize_document):
        first = await store_library_item(_client, "admin-user", item, "job-1")
        second = await store_library_item(_client, "admin-user", item, "job-1-retry")

    assert first == second == fixed_id
    rows = rows_inserted_into(tables, "audiobooks")
    assert {row["id"] for row in rows} == {fixed_id}
    # 작품명이 제목이어야 한다 — 작업 라벨("오디세이 · 1/2 제1권")이 아니다.
    assert rows[0]["title"] == "오디세이"


@pytest.mark.asyncio
async def test_list_library_hides_parts_so_a_series_shows_as_one_card(mock_supabase):
    """24권짜리를 등록해도 서점 화면이 그 작품으로 도배되지 않아야 한다."""
    mock_supabase.table().select().eq().eq().is_().order().execute.return_value = MagicMock(data=[{
        "id": "work-1", "user_id": "admin-user", "title": "오디세이",
        "is_library": True, "library_status": "published",
        "library_part_of": None, "library_part_number": 1, "duration_seconds": 120,
    }])
    # 딸린 부 2개(2부·3부). 목록에서는 서명 URL 없이 요약만 받는다.
    mock_supabase.table().select().in_().execute.return_value = MagicMock(data=[
        {"library_part_of": "work-1", "duration_seconds": 130},
        {"library_part_of": "work-1", "duration_seconds": 150},
    ])
    mock_supabase.storage.from_().create_signed_url.return_value = {"signedURL": "https://example.com/signed"}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/library")

    assert response.status_code == 200
    items = response.json()["library"]
    assert len(items) == 1
    assert items[0]["part_count"] == 3
    assert items[0]["total_duration_seconds"] == 400

    # 부를 걸러내는 조건이 실제로 걸렸는지 본다. 이게 빠지면 목록에 24줄이 뜬다.
    is_calls = mock_supabase.table().select().eq().eq().is_.call_args_list
    assert ("library_part_of", "null") in [call.args for call in is_calls]


@pytest.mark.asyncio
async def test_get_library_item_returns_parts_in_order_including_part_one(mock_supabase):
    """1부는 작품 대표 행 자신이라 part_of 조회에 걸리지 않는다. 목록 맨
    앞에 직접 넣지 않으면 재생목록이 2부부터 시작한다."""
    work_row = {
        "id": "work-1", "user_id": "admin-user", "title": "오디세이",
        "is_library": True, "library_status": "published",
        "library_part_of": None, "library_part_number": 1,
        "library_part_title": "제1권", "duration_seconds": 120,
    }
    mock_supabase.table().select().eq().eq().eq().maybe_single().execute.return_value = \
        MagicMock(data=work_row)
    mock_supabase.table().select().eq().order().execute.return_value = MagicMock(data=[
        {"id": "part-2", "user_id": "admin-user", "title": "오디세이",
         "library_part_of": "work-1", "library_part_number": 2,
         "library_part_title": "제2권", "duration_seconds": 130},
    ])
    mock_supabase.storage.from_().create_signed_url.return_value = {"signedURL": "https://example.com/signed"}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/library/work-1")

    assert response.status_code == 200
    item = response.json()
    assert [part["part_number"] for part in item["parts"]] == [1, 2]
    assert [part["part_title"] for part in item["parts"]] == ["제1권", "제2권"]
    assert item["part_count"] == 2
    assert item["total_duration_seconds"] == 250


@pytest.mark.asyncio
async def test_get_library_item_returns_no_parts_for_a_single_work(mock_supabase):
    """단권은 parts가 비어 있다. 화면이 목차를 그리지 않게 하는 신호다."""
    mock_supabase.table().select().eq().eq().eq().maybe_single().execute.return_value = MagicMock(data={
        "id": "book-1", "user_id": "admin-user", "title": "도덕경",
        "is_library": True, "library_status": "published",
        "library_part_of": None, "library_part_number": None, "duration_seconds": 90,
    })
    mock_supabase.storage.from_().create_signed_url.return_value = {"signedURL": "https://example.com/signed"}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/library/book-1")

    assert response.status_code == 200
    item = response.json()
    assert item["parts"] == []
    assert item["part_count"] == 1
    assert item["total_duration_seconds"] == 90


@pytest.mark.asyncio
async def test_update_library_status_propagates_to_parts(mock_supabase):
    """작품만 published로 바꾸고 부를 review로 두면, 목록에는 보이는데
    재생이 되지 않는 작품이 만들어진다."""
    with patch("routes.library.require_admin_user", return_value="admin-user"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.patch(
                "/api/admin/library/work-1", json={"status": "published"}, headers=_auth_headers())

    assert response.status_code == 200
    eq_calls = [call.args for call in mock_supabase.table().update().eq.call_args_list]
    assert ("id", "work-1") in eq_calls
    assert ("library_part_of", "work-1") in eq_calls


@pytest.mark.asyncio
async def test_part_inherits_the_works_current_status_not_the_queued_one(mock_supabase_tables):
    """24부짜리는 합성에 20분 가까이 걸린다. 그동안 관리자가 앞부분을 확인하고
    발행을 누르면, 그 뒤에 만들어지는 부만 review로 남아 작품과 갈린다.
    실제로 오디세이 등록에서 1~15부는 published, 16~24부는 review가 됐다.
    """
    from routes.library import store_library_item

    client, tables = mock_supabase_tables
    # 작품 행은 이미 published로 바뀌어 있다.
    audiobooks = tables.setdefault("audiobooks", MagicMock())
    audiobooks.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = \
        MagicMock(data={"library_status": "published"})

    item = {
        "title": "오디세이 · 20/24 제20권", "work_title": "오디세이", "content": "본문",
        "audiobook_id": "part-20-id", "part_of": "work-id", "part_number": 20,
        "part_title": "제20권", "status": "review",   # ← 큐잉 때의 값
    }

    with patch("routes.tts.synthesize_document_to_file", side_effect=_fake_synthesize_document):
        await store_library_item(client, "admin-user", item, "job-20")

    row = rows_inserted_into(tables, "audiobooks")[0]
    assert row["library_status"] == "published", "부가 작품의 현재 상태를 따라야 한다"


@pytest.mark.asyncio
async def test_single_work_keeps_its_queued_status(mock_supabase_tables):
    """단권은 따라갈 작품이 없다. 큐잉 때의 status를 그대로 쓴다 —
    기본값 review가 유지돼야 검토 없이 공개되는 일이 없다."""
    from routes.library import store_library_item

    client, tables = mock_supabase_tables
    item = {"title": "도덕경", "content": "도가도 비상도", "part_of": None, "status": "review"}

    with patch("routes.tts.synthesize_document_to_file", side_effect=_fake_synthesize_document):
        await store_library_item(client, "admin-user", item, "job-single")

    assert rows_inserted_into(tables, "audiobooks")[0]["library_status"] == "review"
