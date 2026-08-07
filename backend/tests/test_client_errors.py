"""조용한 실패 보고(/api/client-errors) 테스트.

이 엔드포인트가 생긴 이유는 하나다. 클라이언트는 재생이 안 끊기도록 저장
실패를 삼키는데, 그 실패가 아무 데도 남지 않아 `playback_history`가 몇 주
동안 통째로 비어 있는데도 아무도 몰랐다. 그래서 여기서 지켜야 할 불변조건은
"보고는 어떤 경우에도 조용히 사라지지 않는다"이다.
"""
from unittest.mock import MagicMock, patch

import httpx
import pytest

from tests.conftest import rows_inserted_into
from main import app


def _auth_headers(user_id="test_user_id"):
    from auth import create_access_token
    return {"Authorization": f"Bearer {create_access_token({'sub': user_id})}"}


async def _post(payload, headers=None):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        return await client.post("/api/client-errors", json=payload, headers=headers or {})


@pytest.mark.asyncio
async def test_records_swallowed_failure(mock_supabase_tables):
    _client, tables = mock_supabase_tables

    response = await _post(
        {"scope": "playback_save", "message": "Error: 500 Internal Server Error"},
        _auth_headers(),
    )

    assert response.status_code == 200
    rows = rows_inserted_into(tables, "client_errors")
    assert len(rows) == 1
    assert rows[0]["scope"] == "playback_save"
    assert rows[0]["user_id"] == "test_user_id"
    assert "500" in rows[0]["message"]


@pytest.mark.asyncio
async def test_accepts_anonymous_reports(mock_supabase_tables):
    # 가입만 하고 아무것도 안 한 사용자가 무엇에 걸렸는지가 정확히
    # 알고 싶은 것이라, 비로그인 보고를 버리면 만든 의미의 절반이 없어진다.
    _client, tables = mock_supabase_tables

    response = await _post({"scope": "generation", "message": "TypeError: x is not a function"})

    assert response.status_code == 200
    rows = rows_inserted_into(tables, "client_errors")
    assert len(rows) == 1
    assert rows[0]["user_id"] is None


@pytest.mark.asyncio
async def test_expired_token_still_records(mock_supabase_tables):
    _client, tables = mock_supabase_tables

    response = await _post(
        {"scope": "cloud_sync", "message": "네트워크 오류"},
        {"Authorization": "Bearer not-a-valid-token"},
    )

    assert response.status_code == 200
    assert rows_inserted_into(tables, "client_errors")[0]["user_id"] is None


@pytest.mark.asyncio
async def test_rejects_unknown_scope(mock_supabase_tables):
    # 아무 문자열이나 받으면 오타 하나로 지표가 두 갈래로 갈라진다.
    response = await _post({"scope": "아무거나", "message": "..."}, _auth_headers())

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_rejects_empty_message(mock_supabase_tables):
    response = await _post({"scope": "generation", "message": ""}, _auth_headers())

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_truncates_long_message(mock_supabase_tables):
    # 스택 트레이스가 통째로 오면 DB 행 하나가 수십 KB가 된다.
    _client, tables = mock_supabase_tables

    await _post({"scope": "generation", "message": "가" * 5000}, _auth_headers())

    assert len(rows_inserted_into(tables, "client_errors")[0]["message"]) == 500


@pytest.mark.asyncio
async def test_reporting_failure_does_not_raise(mock_supabase_tables):
    """⚠️ 이게 이 파일에서 가장 중요한 테스트다.

    보고가 실패해서 500을 내면 클라이언트가 그것도 삼키고, 결국 없애려던
    침묵이 한 겹 더 생긴다. DB가 죽어 있어도 200이어야 한다.
    """
    client, tables = mock_supabase_tables
    failing = MagicMock()
    failing.insert.side_effect = RuntimeError("supabase down")
    tables["client_errors"] = failing

    response = await _post({"scope": "playback_save", "message": "무언가 실패"}, _auth_headers())

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_metrics_include_client_errors(mock_supabase_tables):
    """관리자 지표에 안 실리면 로그에만 쌓이고 아무도 안 본다."""
    client, tables = mock_supabase_tables
    errors = MagicMock()
    errors.select.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value.data = [
        {"user_id": None, "scope": "playback_save", "message": "500", "created_at": "2026-08-07T10:00:00+00:00"},
    ]
    tables["client_errors"] = errors
    for name in ("users", "audiobooks", "product_events"):
        tables[name] = MagicMock()
        tables[name].select.return_value.execute.return_value.data = []
        tables[name].select.return_value.gte.return_value.execute.return_value.data = []

    with patch("routes.system.require_admin_user", return_value="admin"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
            response = await http.get("/api/admin/metrics", headers=_auth_headers())

    assert response.status_code == 200
    body = response.json()
    assert body["client_errors_7d"] == 1
    detail = body["metric_details"]["client_errors_7d"][0]
    assert detail["name"] == "재생 위치 저장"
    assert detail["email"] == "비로그인"


@pytest.mark.asyncio
async def test_metrics_survive_client_errors_query_failure(mock_supabase_tables):
    """조용한 실패 조회가 깨졌다고 관리자 통계 전체가 죽으면 안 된다."""
    client, tables = mock_supabase_tables
    broken = MagicMock()
    broken.select.side_effect = RuntimeError("relation does not exist")
    tables["client_errors"] = broken
    for name in ("users", "audiobooks", "product_events"):
        tables[name] = MagicMock()
        tables[name].select.return_value.execute.return_value.data = []
        tables[name].select.return_value.gte.return_value.execute.return_value.data = []

    with patch("routes.system.require_admin_user", return_value="admin"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
            response = await http.get("/api/admin/metrics", headers=_auth_headers())

    assert response.status_code == 200
    assert response.json()["client_errors_7d"] == 0
