import pytest
import httpx
from unittest.mock import patch
from main import app, jobs


def _owner_from_header(authorization):
    return authorization.split()[-1]

@pytest.mark.asyncio
async def test_get_job_status_pending():
    job_id = "test_job_1"
    jobs[job_id] = {
        "status": "pending",
        "progress": 0.0,
        "total": 10,
        "user_id": "owner",
    }
    
    with patch("main.require_user_id", side_effect=_owner_from_header):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(f"/api/job/{job_id}", headers={"Authorization": "Bearer owner"})
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "pending"
        
    del jobs[job_id]

@pytest.mark.asyncio
async def test_get_job_status_generating():
    job_id = "test_job_2"
    jobs[job_id] = {
        "status": "generating",
        "progress": 5.0,
        "total": 10,
        "user_id": "owner",
    }
    
    with patch("main.require_user_id", side_effect=_owner_from_header):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(f"/api/job/{job_id}", headers={"Authorization": "Bearer owner"})
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "generating"
        
    del jobs[job_id]


@pytest.mark.asyncio
async def test_get_job_status_processing_includes_chunk_progress():
    job_id = "test_job_progress"
    jobs[job_id] = {
        "status": "processing",
        "completed_chunks": 2,
        "total_chunks": 5,
        "user_id": "owner",
    }

    with patch("main.require_user_id", side_effect=_owner_from_header):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(f"/api/job/{job_id}", headers={"Authorization": "Bearer owner"})

    assert response.status_code == 200
    assert response.json() == {
        "status": "processing",
        "error": None,
        "completed_chunks": 2,
        "total_chunks": 5,
    }
    del jobs[job_id]

@pytest.mark.asyncio
async def test_get_job_status_not_found():
    with patch("main.require_user_id", return_value="owner"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/job/non_existent_job_id", headers={"Authorization": "Bearer owner"})
            assert response.status_code == 404
            assert "작업을 찾을 수 없습니다" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_job_status_rejects_other_user():
    jobs["private_job"] = {"status": "pending", "user_id": "owner"}

    with patch("main.require_user_id", side_effect=_owner_from_header):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/job/private_job", headers={"Authorization": "Bearer other"})

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_job_status_rejects_other_anonymous_session():
    jobs["anonymous_job"] = {
        "status": "pending",
        "user_id": "anonymous:anonymous-session-123456",
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/job/anonymous_job",
            headers={"X-Anonymous-Session": "anonymous-session-654321"},
        )

    assert response.status_code == 403
    del jobs["anonymous_job"]
