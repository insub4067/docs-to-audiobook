import pytest
import httpx
from unittest.mock import patch, MagicMock
from main import app


@pytest.fixture
def mock_supabase():
    with patch("auth.get_supabase_client") as mock_get_client:
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        yield mock_client


@pytest.fixture
def mock_auth():
    with patch("routes.folders.require_user_id") as mock_req_user:
        mock_req_user.return_value = "test_user_id"
        yield mock_req_user


@pytest.mark.asyncio
async def test_create_folder_at_root(mock_supabase, mock_auth):
    mock_supabase.table().insert().execute.return_value = MagicMock(
        data=[{"id": "f1", "user_id": "test_user_id", "name": "소설", "parent_folder_id": None}]
    )

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/folders", json={"name": "소설"}, headers={"Authorization": "Bearer fake_token"}
        )

    assert response.status_code == 200
    assert response.json()["name"] == "소설"


@pytest.mark.asyncio
async def test_create_folder_rejects_empty_name(mock_supabase, mock_auth):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/folders", json={"name": "  "}, headers={"Authorization": "Bearer fake_token"}
        )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_folder_rejects_missing_parent(mock_supabase, mock_auth):
    mock_supabase.table().select().eq().eq().execute.return_value = MagicMock(data=[])

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/folders",
            json={"name": "하위폴더", "parent_folder_id": "does-not-exist"},
            headers={"Authorization": "Bearer fake_token"},
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_root_folder_contents(mock_supabase, mock_auth):
    folders_table = MagicMock()
    folders_table.select().eq().is_().order().execute.return_value = MagicMock(
        data=[{"id": "f1", "name": "소설", "parent_folder_id": None}]
    )

    audiobooks_table = MagicMock()
    audiobooks_table.select().eq().is_().order().execute.return_value = MagicMock(data=[])

    def table_side_effect(name):
        return {"folders": folders_table, "audiobooks": audiobooks_table}[name]

    mock_supabase.table.side_effect = table_side_effect

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/folders", headers={"Authorization": "Bearer fake_token"})

    assert response.status_code == 200
    data = response.json()
    assert data["current_folder"] is None
    assert data["folders"] == [{"id": "f1", "name": "소설", "parent_folder_id": None}]
    assert data["audiobooks"] == []


@pytest.mark.asyncio
async def test_list_folder_contents_rejects_missing_folder(mock_supabase, mock_auth):
    mock_supabase.table().select().eq().eq().execute.return_value = MagicMock(data=[])

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/folders", params={"parent_id": "does-not-exist"}, headers={"Authorization": "Bearer fake_token"}
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_folder_rename(mock_supabase, mock_auth):
    mock_supabase.table().update().eq().eq().execute.return_value = MagicMock(
        data=[{"id": "f1", "name": "새 이름"}]
    )

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            "/api/folders/f1", json={"name": " 새 이름 "}, headers={"Authorization": "Bearer fake_token"}
        )

    assert response.status_code == 200
    assert response.json()["name"] == "새 이름"


@pytest.mark.asyncio
async def test_update_folder_rejects_moving_into_itself(mock_supabase, mock_auth):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            "/api/folders/f1",
            json={"parent_folder_id": "f1"},
            headers={"Authorization": "Bearer fake_token"},
        )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_update_folder_rejects_empty_payload(mock_supabase, mock_auth):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            "/api/folders/f1", json={}, headers={"Authorization": "Bearer fake_token"}
        )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_delete_folder_moves_contents_to_parent(mock_supabase, mock_auth):
    folders_table = MagicMock()
    folders_table.select().eq().eq().execute.return_value = MagicMock(
        data=[{"id": "f2", "user_id": "test_user_id", "parent_folder_id": "f1"}]
    )
    folders_table.delete().eq().eq().execute.return_value = MagicMock(data=[{"id": "f2"}])

    audiobooks_table = MagicMock()

    def table_side_effect(name):
        return {"folders": folders_table, "audiobooks": audiobooks_table}[name]

    mock_supabase.table.side_effect = table_side_effect

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.delete("/api/folders/f2", headers={"Authorization": "Bearer fake_token"})

    assert response.status_code == 200
    assert response.json() == {"deleted": "f2"}
    # 하위 폴더도, 그 안의 오디오북도 삭제된 폴더의 상위(f1)로 옮겨져야 한다
    folders_table.update.assert_any_call({"parent_folder_id": "f1"})
    audiobooks_table.update.assert_any_call({"folder_id": "f1"})


@pytest.mark.asyncio
async def test_delete_folder_not_found(mock_supabase, mock_auth):
    mock_supabase.table().select().eq().eq().execute.return_value = MagicMock(data=[])

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.delete("/api/folders/does-not-exist", headers={"Authorization": "Bearer fake_token"})

    assert response.status_code == 404


def _folders_supabase(rows):
    """folders 조회만 흉내내는 최소 목."""
    supabase = MagicMock()
    query = MagicMock()
    query.eq.return_value = query
    query.execute.return_value = MagicMock(data=rows)
    supabase.table.return_value.select.return_value = query
    return supabase


# A → B → C 구조. A를 C 밑으로 옮기면 A → B → C → A 고리가 된다.
NESTED_FOLDERS = [
    {"id": "A", "parent_folder_id": None},
    {"id": "B", "parent_folder_id": "A"},
    {"id": "C", "parent_folder_id": "B"},
]


def test_move_into_descendant_is_detected():
    """자기 자신만 막으면 A를 C 밑으로 넣어 고리를 만들 수 있었다. 고리에
    들어간 폴더는 어느 루트에서도 도달할 수 없어 화면에서 사라진다."""
    from routes.folders import _rejects_move_into_own_subtree

    supabase = _folders_supabase(NESTED_FOLDERS)

    assert _rejects_move_into_own_subtree(supabase, "u1", "A", "C") is True
    assert _rejects_move_into_own_subtree(supabase, "u1", "A", "B") is True


def test_move_to_unrelated_folder_is_allowed():
    """방어가 정상 이동을 막으면 안 된다."""
    from routes.folders import _rejects_move_into_own_subtree

    supabase = _folders_supabase(NESTED_FOLDERS + [{"id": "D", "parent_folder_id": None}])

    assert _rejects_move_into_own_subtree(supabase, "u1", "C", "D") is False
    assert _rejects_move_into_own_subtree(supabase, "u1", "A", "D") is False


def test_existing_cycle_does_not_hang_the_walk():
    """데이터가 이미 깨져 고리가 있어도 무한히 돌면 안 된다."""
    from routes.folders import _rejects_move_into_own_subtree

    supabase = _folders_supabase([
        {"id": "X", "parent_folder_id": "Y"},
        {"id": "Y", "parent_folder_id": "X"},
    ])

    assert _rejects_move_into_own_subtree(supabase, "u1", "Z", "X") is False


@pytest.mark.asyncio
async def test_update_folder_rejects_moving_into_descendant(mock_supabase, mock_auth):
    query = MagicMock()
    query.eq.return_value = query
    # 상위 폴더 존재 확인과 전체 목록 조회가 같은 목을 쓴다.
    query.execute.return_value = MagicMock(data=NESTED_FOLDERS)
    mock_supabase.table.return_value.select.return_value = query

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            "/api/folders/A", json={"parent_folder_id": "C"},
            headers={"Authorization": "Bearer fake_token"},
        )

    assert response.status_code == 400
    assert "하위 폴더" in response.json()["detail"]
