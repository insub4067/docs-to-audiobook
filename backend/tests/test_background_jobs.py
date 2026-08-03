"""관리자 대용량 문서 백그라운드 처리 테스트.

docs/large-admin-background-jobs.md 참고. 여기서는 이 기능 고유의 로직만
검증한다: 백그라운드 작업 동시성 제한(429), 결과 저장 순서(고아 방지),
재시작 후 재개, 전체 재시도(all or nothing).

이 기능의 실제 구현은 routes/tts.py(라우트·합성 엔진·백그라운드 작업이
서로 강하게 얽혀 있어 한 모듈에 있다)에 있고, 디스크 여유 판단은
state.py에 있다. patch 대상은 그 함수를 실제로 호출하는 코드가 정의된
모듈이어야 한다 — main.X를 patch해도 각 모듈 내부의 호출에는 적용되지
않는다.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

import main
import state
from routes import tts


@pytest.fixture
def mock_supabase():
    with patch("auth.get_supabase_client") as mock_get_client:
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        yield mock_client


@pytest.fixture(autouse=True)
def restore_jobs_state():
    existing_job_ids = set(state.jobs)
    yield
    for job_id in set(state.jobs) - existing_job_ids:
        state.jobs.pop(job_id, None)


def _seed_large_text(text_id="large-doc", max_synth_chars=None):
    state.text_storage[text_id] = {
        "filename": "large.pdf",
        "text": "관리자 대용량 문서 테스트 본문입니다.",
        "char_count": 20,
        "max_synth_chars": max_synth_chars or state.MAX_ADMIN_SYNTH_CHARS,
        "created_at": 0,
        "access_token": "text-token",
    }


# ---- /api/synthesize 대용량 분기: 동시성 제한 ----

@pytest.mark.asyncio
async def test_synthesize_large_text_starts_background_job(mock_supabase):
    import httpx

    _seed_large_text()
    # 진행 중인 작업이 없다.
    mock_supabase.table().select().in_().limit().execute.return_value = MagicMock(data=[])

    with patch("state.require_user_id", return_value="admin-user"), \
         patch("routes.tts.process_background_synthesis_task"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
            response = await client.post(
                "/api/synthesize",
                data={"text_id": "large-doc", "text_access_token": "text-token"},
                headers={"Authorization": "Bearer fake"},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["background_started"] is True
    assert "job_id" in data
    # 진행 중 작업이 없었으므로 새 작업이 큐에 들어갔어야 한다.
    mock_supabase.table().insert.assert_called_once()
    inserted = mock_supabase.table().insert.call_args[0][0]
    assert inserted["id"] == data["job_id"]
    assert inserted["source_text"] == state.text_storage.get("large-doc", {}).get("text", inserted["source_text"])

    state.jobs.pop(data["job_id"], None)
    state.text_storage.pop("large-doc", None)


@pytest.mark.asyncio
async def test_synthesize_large_text_with_folder_stores_folder_id(mock_supabase):
    # 폴더 안에서 대용량 문서를 추가하면 그 폴더 id가 작업 큐 행에도
    # 실려야, 완료 후 _store_background_audiobook이 같은 폴더에 저장한다.
    import httpx

    _seed_large_text()
    mock_supabase.table().select().eq().eq().execute.return_value = MagicMock(data=[{"id": "folder-1"}])
    mock_supabase.table().select().in_().limit().execute.return_value = MagicMock(data=[])

    with patch("state.require_user_id", return_value="admin-user"), \
         patch("routes.tts.process_background_synthesis_task"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
            response = await client.post(
                "/api/synthesize",
                data={"text_id": "large-doc", "text_access_token": "text-token", "folder_id": "folder-1"},
                headers={"Authorization": "Bearer fake"},
            )

    assert response.status_code == 200
    data = response.json()
    inserted = mock_supabase.table().insert.call_args[0][0]
    assert inserted["folder_id"] == "folder-1"

    state.jobs.pop(data["job_id"], None)
    state.text_storage.pop("large-doc", None)


@pytest.mark.asyncio
async def test_synthesize_large_text_rejects_folder_not_owned(mock_supabase):
    import httpx

    _seed_large_text()
    mock_supabase.table().select().eq().eq().execute.return_value = MagicMock(data=[])

    with patch("state.require_user_id", return_value="admin-user"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
            response = await client.post(
                "/api/synthesize",
                data={"text_id": "large-doc", "text_access_token": "text-token", "folder_id": "not-mine"},
                headers={"Authorization": "Bearer fake"},
            )

    assert response.status_code == 404
    mock_supabase.table().insert.assert_not_called()
    state.text_storage.pop("large-doc", None)


@pytest.mark.asyncio
async def test_synthesize_large_text_rejected_when_job_already_running(mock_supabase):
    import httpx

    _seed_large_text()
    # 이미 진행 중인 작업이 있다.
    mock_supabase.table().select().in_().limit().execute.return_value = MagicMock(
        data=[{"id": "already-running"}]
    )

    with patch("state.require_user_id", return_value="admin-user"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
            response = await client.post(
                "/api/synthesize",
                data={"text_id": "large-doc", "text_access_token": "text-token"},
                headers={"Authorization": "Bearer fake"},
            )

    assert response.status_code == 429
    assert "이미 진행 중인" in response.json()["detail"]


@pytest.mark.asyncio
async def test_synthesize_large_text_rejected_when_disk_is_low(mock_supabase):
    # 고정 상한이 아니라 그 순간의 실제 여유 디스크로 판단한다 — 여유가
    # 거의 없다고 응답하면(디스크의 남은 용량 반환값을 가짜로 아주
    # 작게 준다) 큐에 올리지 않고 거절해야 한다.
    import httpx
    from unittest.mock import Mock

    _seed_large_text()
    mock_supabase.table().select().in_().limit().execute.return_value = MagicMock(data=[])

    fake_usage = Mock(free=1024)  # 1KB밖에 안 남았다고 가정
    with patch("state.require_user_id", return_value="admin-user"), \
         patch("state.shutil.disk_usage", return_value=fake_usage):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
            response = await client.post(
                "/api/synthesize",
                data={"text_id": "large-doc", "text_access_token": "text-token"},
                headers={"Authorization": "Bearer fake"},
            )

    assert response.status_code == 413
    assert "디스크 여유가 부족" in response.json()["detail"]
    mock_supabase.table().insert.assert_not_called()

    state.text_storage.pop("large-doc", None)


def test_has_enough_disk_for_synthesis_uses_real_free_space(tmp_path, monkeypatch):
    # 실제 shutil.disk_usage를 그대로 쓰되, 대상 디렉터리만 바꿔서 순수
    # 계산 로직(추정 바이트 vs 여유- 예비분)을 검증한다.
    monkeypatch.setattr(state, "JOB_AUDIO_DIR", str(tmp_path))
    assert state._has_enough_disk_for_synthesis(1) is True  # 글자 1개는 항상 충분하다

    huge_char_count = 10**15  # 어떤 실제 디스크보다도 훨씬 큰 값
    assert state._has_enough_disk_for_synthesis(huge_char_count) is False


@pytest.mark.asyncio
async def test_synthesize_large_text_requires_login(mock_supabase):
    _seed_large_text()
    import httpx
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post(
            "/api/synthesize",
            data={"text_id": "large-doc", "text_access_token": "text-token"},
            headers={"X-Anonymous-Session": "anonymous-session-123456"},
        )
    assert response.status_code == 401
    state.text_storage.pop("large-doc", None)


# ---- _store_background_audiobook: 결과 저장 순서(고아 방지) ----

def test_store_background_audiobook_uploads_before_insert(mock_supabase, tmp_path):
    audio_file = tmp_path / "out.mp3"
    audio_file.write_bytes(b"fake-mp3-bytes")
    job = {"audio_path": str(audio_file), "sentences": [{"text": "문장", "start": 0, "end": 1}]}

    audiobook_id = tts._store_background_audiobook("user-1", "제목", job)

    storage = mock_supabase.storage.from_()
    assert storage.upload.call_count == 2
    mock_supabase.table().insert.assert_called_once()
    inserted = mock_supabase.table().insert.call_args[0][0]
    assert inserted["id"] == audiobook_id
    assert inserted["user_id"] == "user-1"


def test_store_background_audiobook_rolls_back_mp3_on_sentences_failure(mock_supabase, tmp_path):
    audio_file = tmp_path / "out.mp3"
    audio_file.write_bytes(b"fake-mp3-bytes")
    job = {"audio_path": str(audio_file), "sentences": [{"text": "문장", "start": 0, "end": 1}]}

    storage = mock_supabase.storage.from_()
    storage.upload.side_effect = [None, Exception("sentences 업로드 실패")]

    with pytest.raises(Exception, match="sentences 업로드 실패"):
        tts._store_background_audiobook("user-1", "제목", job)

    # mp3는 이미 올라갔으니 고아로 남기지 말고 지워야 한다.
    storage.remove.assert_called_once()
    removed_paths = storage.remove.call_args[0][0]
    assert len(removed_paths) == 1
    # 실패했으니 DB 행은 만들면 안 된다.
    mock_supabase.table().insert.assert_not_called()


def test_store_background_audiobook_includes_folder_id(mock_supabase, tmp_path):
    audio_file = tmp_path / "out.mp3"
    audio_file.write_bytes(b"fake-mp3-bytes")
    job = {"audio_path": str(audio_file), "sentences": []}
    mock_supabase.table().select().eq().eq().execute.return_value = MagicMock(data=[{"id": "folder-1"}])

    tts._store_background_audiobook("user-1", "제목", job, "folder-1")

    inserted = mock_supabase.table().insert.call_args[0][0]
    assert inserted["folder_id"] == "folder-1"


def test_store_background_audiobook_falls_back_to_root_when_folder_deleted(mock_supabase, tmp_path):
    # 큐에 올릴 때는 폴더가 있었지만, 몇 시간짜리 작업이 끝나기 전에
    # 사용자가 그 폴더를 지웠을 수 있다 — 저장 자체를 실패시키지 말고
    # 루트에 저장해야 한다.
    audio_file = tmp_path / "out.mp3"
    audio_file.write_bytes(b"fake-mp3-bytes")
    job = {"audio_path": str(audio_file), "sentences": []}
    mock_supabase.table().select().eq().eq().execute.return_value = MagicMock(data=[])

    tts._store_background_audiobook("user-1", "제목", job, "deleted-folder")

    inserted = mock_supabase.table().insert.call_args[0][0]
    assert inserted["folder_id"] is None


# ---- resume_background_synthesis_jobs: 재시작 후 재개 ----

@pytest.mark.asyncio
async def test_resume_reschedules_queued_jobs(mock_supabase):
    mock_supabase.table().select().in_().execute.return_value = MagicMock(
        data=[{
            "id": "job-resume-1",
            "user_id": "user-1",
            "title": "재개될 문서",
            "source_text": "원문 텍스트",
            "voice": "ko-KR-HyunsuMultilingualNeural",
            "rate": "+0%",
            "pitch": "+0Hz",
            "status": "queued",
        }]
    )
    # 선점(claim) update가 성공해 영향받은 행을 돌려준다.
    mock_supabase.table().update().eq().eq().execute.return_value = MagicMock(
        data=[{"id": "job-resume-1"}]
    )

    with patch("routes.tts.process_background_synthesis_task", new_callable=AsyncMock) as mock_task:
        await tts.resume_background_synthesis_jobs()
        await __import__("asyncio").sleep(0)  # create_task로 예약된 코루틴이 시작되게 한 틱 양보

    # DB에는 예전 edge-tts short_name이 그대로 저장돼 있지만, 재개 시점에
    # 공급자 중립 voice_key("ko_male_warm")로 정규화되어 전달돼야 한다.
    mock_task.assert_called_once_with(
        "job-resume-1", "user-1", "재개될 문서", "원문 텍스트",
        "ko_male_warm", "+0%", "+0Hz", None,
    )
    assert state.jobs["job-resume-1"]["status"] == "processing"
    state.jobs.pop("job-resume-1", None)


@pytest.mark.asyncio
async def test_resume_reschedules_queued_jobs_with_folder_id(mock_supabase):
    mock_supabase.table().select().in_().execute.return_value = MagicMock(
        data=[{
            "id": "job-resume-2",
            "user_id": "user-1",
            "title": "재개될 문서",
            "source_text": "원문 텍스트",
            "voice": "ko_male_warm",
            "rate": "+0%",
            "pitch": "+0Hz",
            "status": "queued",
            "folder_id": "folder-1",
        }]
    )
    mock_supabase.table().update().eq().eq().execute.return_value = MagicMock(
        data=[{"id": "job-resume-2"}]
    )

    with patch("routes.tts.process_background_synthesis_task", new_callable=AsyncMock) as mock_task:
        await tts.resume_background_synthesis_jobs()
        await __import__("asyncio").sleep(0)

    mock_task.assert_called_once_with(
        "job-resume-2", "user-1", "재개될 문서", "원문 텍스트",
        "ko_male_warm", "+0%", "+0Hz", "folder-1",
    )
    state.jobs.pop("job-resume-2", None)


@pytest.mark.asyncio
async def test_resume_skips_when_another_process_already_claimed(mock_supabase):
    # 배포 중 이전/새 프로세스가 잠깐 겹쳐 같은 행을 먼저 가져간 경우를
    # 흉내낸다: 선점 update가 아무 행도 바꾸지 못했다(빈 결과).
    mock_supabase.table().select().in_().execute.return_value = MagicMock(
        data=[{
            "id": "job-already-claimed",
            "user_id": "user-1",
            "title": "t",
            "source_text": "원문",
            "voice": "v", "rate": "r", "pitch": "p",
            "status": "processing",
        }]
    )
    mock_supabase.table().update().eq().eq().execute.return_value = MagicMock(data=[])

    with patch("routes.tts.process_background_synthesis_task", new_callable=AsyncMock) as mock_task:
        await tts.resume_background_synthesis_jobs()
        await __import__("asyncio").sleep(0)

    mock_task.assert_not_called()
    assert "job-already-claimed" not in state.jobs


@pytest.mark.asyncio
async def test_resume_skips_rows_without_source_text(mock_supabase):
    # source_text가 없는 행은(예: 완료 직후 잠깐 조회된 경우) 재개 대상이 아니다.
    mock_supabase.table().select().in_().execute.return_value = MagicMock(
        data=[{"id": "job-no-text", "user_id": "user-1", "title": "t",
               "source_text": None, "voice": "v", "rate": "r", "pitch": "p", "status": "queued"}]
    )

    with patch("routes.tts.process_background_synthesis_task", new_callable=AsyncMock) as mock_task:
        await tts.resume_background_synthesis_jobs()
        await __import__("asyncio").sleep(0)

    mock_task.assert_not_called()
    assert "job-no-text" not in state.jobs


# ---- process_background_synthesis_task: 전체 재시도(all or nothing) ----
#
# 청크 재시도(synthesize_chunk)로도 못 살린 실패는 asyncio.gather가
# 파트 하나만 죽어도 문서 전체를 실패시킨다(routes/tts.py의
# synthesize_document_to_file 근처). 몇 시간짜리 작업이 통째로 날아가는
# 걸 막기 위해, 문서 전체를 처음부터 최대 3번 다시 시도한다.

@pytest.mark.asyncio
async def test_process_background_synthesis_task_succeeds_first_try(mock_supabase, tmp_path):
    async def fake_process(job_id, raw_text, voice, rate, pitch):
        audio_path = tmp_path / f"{job_id}.mp3"
        audio_path.write_bytes(b"fake-audio")
        state.jobs[job_id]["status"] = "completed"
        state.jobs[job_id]["audio_path"] = str(audio_path)
        state.jobs[job_id]["sentences"] = []

    with patch("routes.tts.process_synthesis_task", side_effect=fake_process), \
         patch("routes.tts._store_background_audiobook", return_value="audiobook-1") as mock_store, \
         patch("routes.tts.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await tts.process_background_synthesis_task(
            "job-first-try", "user-1", "제목", "원문", "voice", "+0%", "+0Hz"
        )

    mock_store.assert_called_once()
    mock_sleep.assert_not_called()  # 한 번에 성공했으니 재시도 대기가 없어야 한다
    update_calls = mock_supabase.table().update.call_args_list
    assert any(call.args[0].get("status") == "completed" for call in update_calls)
    state.jobs.pop("job-first-try", None)


@pytest.mark.asyncio
async def test_background_completion_updates_database_before_push(mock_supabase):
    events = []

    def update_job(payload):
        query = MagicMock()
        query.eq.return_value = query
        query.execute.side_effect = lambda: events.append(("execute", payload.get("status"))) or MagicMock()
        return query

    mock_supabase.table().update.side_effect = update_job

    async def complete_job(job_id, *_):
        state.jobs[job_id]["status"] = "completed"

    with patch("routes.tts.process_synthesis_task", side_effect=complete_job), \
         patch("routes.tts._store_background_audiobook", return_value="book-1"), \
         patch("routes.tts.send_background_job_ready", side_effect=lambda *_: events.append(("push", None))):
        await tts.process_background_synthesis_task(
            "job-1", "user-1", "제목", "원문", "voice", "+0%", "+0Hz"
        )

    completed_index = events.index(("execute", "completed"))
    push_index = events.index(("push", None))
    assert completed_index < push_index


@pytest.mark.asyncio
async def test_push_exception_does_not_overwrite_completed_job(mock_supabase):
    completed_updates = []

    def update_job(payload):
        query = MagicMock()
        query.eq.return_value = query
        query.execute.side_effect = lambda: completed_updates.append(payload.copy()) or MagicMock()
        return query

    mock_supabase.table().update.side_effect = update_job

    async def complete_job(job_id, *_):
        state.jobs[job_id]["status"] = "completed"

    with patch("routes.tts.process_synthesis_task", side_effect=complete_job), \
         patch("routes.tts._store_background_audiobook", return_value="book-1"), \
         patch("routes.tts.send_background_job_ready", side_effect=RuntimeError("push unavailable")), \
         patch("routes.tts.asyncio.sleep", new_callable=AsyncMock):
        await tts.process_background_synthesis_task(
            "job-push-failure", "user-1", "제목", "원문", "voice", "+0%", "+0Hz"
        )

    statuses = [payload.get("status") for payload in completed_updates]
    assert "completed" in statuses
    assert "error" not in statuses
    assert state.jobs["job-push-failure"]["status"] == "completed"


@pytest.mark.asyncio
async def test_process_background_synthesis_task_retries_whole_job_on_failure(mock_supabase, tmp_path):
    attempts = []

    async def fake_process(job_id, raw_text, voice, rate, pitch):
        attempts.append(len(attempts) + 1)
        if len(attempts) == 1:
            state.jobs[job_id]["status"] = "error"
            state.jobs[job_id]["error"] = "청크 하나가 계속 실패했습니다."
        else:
            audio_path = tmp_path / f"{job_id}.mp3"
            audio_path.write_bytes(b"fake-audio")
            state.jobs[job_id]["status"] = "completed"
            state.jobs[job_id]["audio_path"] = str(audio_path)
            state.jobs[job_id]["sentences"] = []

    with patch("routes.tts.process_synthesis_task", side_effect=fake_process), \
         patch("routes.tts._store_background_audiobook", return_value="audiobook-1"), \
         patch("routes.tts.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await tts.process_background_synthesis_task(
            "job-retry-success", "user-1", "제목", "원문", "voice", "+0%", "+0Hz"
        )

    assert len(attempts) == 2  # 첫 시도 실패, 두 번째에 성공
    assert mock_sleep.call_count == 1  # 재시도 사이에 한 번만 쉰다
    assert state.jobs["job-retry-success"]["status"] == "completed"
    state.jobs.pop("job-retry-success", None)


@pytest.mark.asyncio
async def test_process_background_synthesis_task_gives_up_after_max_attempts(mock_supabase):
    async def always_fails(job_id, raw_text, voice, rate, pitch):
        state.jobs[job_id]["status"] = "error"
        state.jobs[job_id]["error"] = "계속 실패합니다."

    with patch("routes.tts.process_synthesis_task", side_effect=always_fails), \
         patch("routes.tts.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await tts.process_background_synthesis_task(
            "job-all-fail", "user-1", "제목", "원문", "voice", "+0%", "+0Hz"
        )

    assert state.jobs["job-all-fail"]["status"] == "error"
    assert state.jobs["job-all-fail"]["error"] == "계속 실패합니다."
    assert mock_sleep.call_count == 2  # 3번 시도, 사이에 2번만 쉰다
    update_calls = mock_supabase.table().update.call_args_list
    assert any(call.args[0].get("status") == "error" for call in update_calls)
    state.jobs.pop("job-all-fail", None)
