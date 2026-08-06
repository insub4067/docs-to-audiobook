"""등록 작업(content_jobs) 테스트 — 뉴스·라이브러리 공용.

이 테이블이 생긴 이유는 원문을 합성 전에 저장하기 위해서다. 예전에는
합성이 실패하면 audiobooks 행이 아예 만들어지지 않아 서버 로그 말고는
아무 흔적도 남지 않았고, 관리자는 무엇이 왜 실패했는지 알 수도 다시
시도할 수도 없었다. 그래서 "실패해도 원문이 남는다"가 가장 중요한
불변조건이다.
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


async def _always_fails(text, voice, rate, pitch, progress_callback=None, provider_name=None):
    raise TimeoutError("TTS 요청 시간 초과")


# 등록 경로 두 개를 같은 표로 돌려, 한쪽만 고쳐지는 일이 없게 한다.
REGISTRATION_PATHS = [
    ("news", "/api/admin/news", "routes.news", '[{"title": "첫 뉴스", "content": "본문입니다.", "category": "국제"}]'),
    ("library", "/api/admin/library", "routes.library", '[{"title": "금강경", "content": "여시아문", "category": "종교·경전"}]'),
]


async def _register(path, module, payload_text, synthesize=_fake_synthesize_document):
    with patch(f"{module}.require_admin_user", return_value="admin-user"), \
         patch(f"{module}.synthesize_document", side_effect=synthesize):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            return await client.post(path, json={"text": payload_text}, headers=_auth_headers())


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,path,module,payload_text", REGISTRATION_PATHS)
async def test_registration_persists_source_text_before_synthesizing(kind, path, module, payload_text, mock_supabase_tables):
    _client, tables = mock_supabase_tables

    response = await _register(path, module, payload_text)

    assert response.status_code == 200
    job_rows = tables["content_jobs"].inserted
    assert len(job_rows) == 1
    assert job_rows[0]["kind"] == kind
    assert job_rows[0]["source_text"]
    assert job_rows[0]["metadata"]["category"] is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,path,module,payload_text", REGISTRATION_PATHS)
async def test_failure_keeps_source_text_and_records_reason(kind, path, module, payload_text, mock_supabase_tables):
    _client, tables = mock_supabase_tables

    response = await _register(path, module, payload_text, synthesize=_always_fails)

    assert response.status_code == 200
    jobs = tables["content_jobs"]
    remaining = list(jobs.rows.values())
    # 실패한 작업은 남아 있어야 하고, 원문은 재시도의 유일한 근거다.
    assert len(remaining) == 1
    assert remaining[0]["status"] == "error"
    assert "TTS 요청 시간 초과" in remaining[0]["error"]
    assert remaining[0]["source_text"]
    assert jobs.deleted == []
    assert rows_inserted_into(tables, "audiobooks") == []


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,path,module,payload_text", REGISTRATION_PATHS)
async def test_success_removes_the_job_row(kind, path, module, payload_text, mock_supabase_tables):
    _client, tables = mock_supabase_tables

    await _register(path, module, payload_text)

    jobs = tables["content_jobs"]
    assert jobs.rows == {}
    assert len(rows_inserted_into(tables, "audiobooks")) == 1
    # queued → processing 을 거쳤는지도 확인한다.
    assert "processing" in jobs.status_updates()


@pytest.mark.asyncio
async def test_list_content_jobs_rejects_non_admin():
    def reject(authorization):
        raise HTTPException(status_code=403, detail="관리자만 접근할 수 있습니다.")

    with patch("routes.content_jobs.require_admin_user", side_effect=reject):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/admin/content-jobs", headers=_auth_headers())
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_content_jobs_shows_failed_news_and_library_together(mock_supabase_tables):
    _client, tables = mock_supabase_tables
    await _register(*REGISTRATION_PATHS[0][1:], synthesize=_always_fails)
    await _register(*REGISTRATION_PATHS[1][1:], synthesize=_always_fails)

    with patch("routes.content_jobs.require_admin_user", return_value="admin-user"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/admin/content-jobs", headers=_auth_headers())

    assert response.status_code == 200
    jobs = response.json()["jobs"]
    assert {job["kind"] for job in jobs} == {"news", "library"}
    assert all(job["status"] == "error" for job in jobs)


@pytest.mark.asyncio
async def test_list_content_jobs_does_not_select_source_text(mock_supabase_tables):
    """작품 한 편 분량의 원문을 목록 응답에 실으면 관리자 화면이 감당하지 못한다."""
    _client, tables = mock_supabase_tables

    with patch("routes.content_jobs.require_admin_user", return_value="admin-user"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            await client.get("/api/admin/content-jobs", headers=_auth_headers())

    assert "source_text" not in tables["content_jobs"].selected_columns


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,path,module,payload_text", REGISTRATION_PATHS)
async def test_retry_rebuilds_from_stored_source_text(kind, path, module, payload_text, mock_supabase_tables):
    _client, tables = mock_supabase_tables
    await _register(path, module, payload_text, synthesize=_always_fails)
    job_id = tables["content_jobs"].inserted[0]["id"]

    with patch("routes.content_jobs.require_admin_user", return_value="admin-user"), \
         patch(f"{module}.synthesize_document", side_effect=_fake_synthesize_document):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(f"/api/admin/content-jobs/{job_id}/retry", headers=_auth_headers())

    assert response.status_code == 200
    # 재시도가 성공했으므로 작업 행은 사라지고 콘텐츠가 만들어져 있다.
    assert tables["content_jobs"].rows == {}
    assert len(rows_inserted_into(tables, "audiobooks")) == 1


@pytest.mark.asyncio
async def test_retry_404s_for_unknown_job(mock_supabase_tables):
    with patch("routes.content_jobs.require_admin_user", return_value="admin-user"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/admin/content-jobs/nope/retry", headers=_auth_headers())

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_removes_the_job(mock_supabase_tables):
    _client, tables = mock_supabase_tables
    await _register(*REGISTRATION_PATHS[0][1:], synthesize=_always_fails)
    job_id = tables["content_jobs"].inserted[0]["id"]

    with patch("routes.content_jobs.require_admin_user", return_value="admin-user"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.delete(f"/api/admin/content-jobs/{job_id}", headers=_auth_headers())

    assert response.status_code == 200
    assert tables["content_jobs"].rows == {}


@pytest.mark.asyncio
async def test_delete_rejects_non_admin():
    def reject(authorization):
        raise HTTPException(status_code=403, detail="관리자만 접근할 수 있습니다.")

    with patch("routes.content_jobs.require_admin_user", side_effect=reject):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.delete("/api/admin/content-jobs/job-1", headers=_auth_headers())
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_progress_is_reported_while_synthesizing(mock_supabase_tables):
    """진행률은 DB가 아니라 프로세스 메모리에 있다 — 목록 응답에 실려야 한다."""
    _client, tables = mock_supabase_tables
    seen = {}

    async def synthesize_and_peek(text, voice, rate, pitch, progress_callback=None, provider_name=None):
        progress_callback(3, 4)
        from routes.content_jobs import _job_progress
        seen.update(_job_progress)
        return await _fake_synthesize_document(text, voice, rate, pitch)

    await _register(*REGISTRATION_PATHS[0][1:], synthesize=synthesize_and_peek)

    assert list(seen.values()) == [75]
