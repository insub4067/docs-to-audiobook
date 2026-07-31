import pytest
import httpx
from main import app, jobs

@pytest.mark.asyncio
async def test_get_job_status_pending():
    job_id = "test_job_1"
    jobs[job_id] = {
        "status": "pending",
        "progress": 0.0,
        "total": 10
    }
    
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/job/{job_id}")
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
        "total": 10
    }
    
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/job/{job_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "generating"
        
    del jobs[job_id]

@pytest.mark.asyncio
async def test_get_job_status_not_found():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/job/non_existent_job_id")
        assert response.status_code == 404
        assert "작업을 찾을 수 없습니다" in response.json()["detail"]
