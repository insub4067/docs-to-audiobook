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
