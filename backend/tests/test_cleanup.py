"""cleanup_expired_files_loop 테스트.

이 루프는 이전에 커버리지 0%였다. while True: ... await asyncio.sleep(600)
구조라 직접 호출하면 테스트가 끝나지 않으므로, 태스크로 띄워 한 번의
반복(본문은 await 지점 없이 전부 동기 실행된다)만 지나가게 한 뒤 취소한다.

SHARED_DIR/JOB_AUDIO_DIR는 반드시 tmp_path로 monkeypatch한다. 실제
프로젝트 디렉터리를 가리키면 이 세션에서 이미 한 번 실제 소스 파일이
파괴된 사고(test_patch.py)와 같은 종류의 위험을 반복하게 된다.
"""
import os
import json
import time
import asyncio
import pytest
import cleanup
import state


@pytest.mark.asyncio
async def test_cleanup_one_iteration(tmp_path, monkeypatch):
    now = time.time()

    shared_dir = tmp_path / "shared"
    job_audio_dir = tmp_path / "job_audio"
    shared_dir.mkdir()
    job_audio_dir.mkdir()
    monkeypatch.setattr(cleanup, "SHARED_DIR", str(shared_dir))
    monkeypatch.setattr(cleanup, "JOB_AUDIO_DIR", str(job_audio_dir))

    # 1) text_storage: 30분(1800s) 넘은 것만 지워져야 한다
    state.text_storage["expired"] = {"created_at": now - 2000}
    state.text_storage["fresh"] = {"created_at": now}

    # 2) jobs: 30분 넘은 것은 지워지고, 딸린 오디오 파일도 삭제돼야 한다
    expired_audio = job_audio_dir / "expired_job.mp3"
    expired_audio.write_bytes(b"audio")
    state.jobs["expired_job"] = {"created_at": now - 2000, "audio_path": str(expired_audio)}
    state.jobs["fresh_job"] = {"created_at": now, "audio_path": None}

    # 3) shared: 24시간(86400s)이 지나면 메타데이터와 무관하게 지워져야 한다
    def make_share(share_id, created_at, never_expire=False):
        d = shared_dir / share_id
        d.mkdir()
        meta = {"created_at": created_at}
        if never_expire:
            meta["never_expire"] = True
        (d / "meta.json").write_text(json.dumps(meta))

    make_share("expired_share", now - 90000)
    make_share("fresh_share", now)
    make_share("legacy_never_expire_share", now - 90000, never_expire=True)

    # 4) job_audio 고아 파일: jobs에 없는 파일도 30분 지나면 지워져야 한다
    #    (서버 재시작 등으로 jobs 딕셔너리가 비어도 디스크에는 남는 경우)
    orphan_old = job_audio_dir / "orphan_old.mp3"
    orphan_old.write_bytes(b"old")
    orphan_new = job_audio_dir / "orphan_new.mp3"
    orphan_new.write_bytes(b"new")
    old_mtime = now - 2000
    os.utime(orphan_old, (old_mtime, old_mtime))

    # 루프의 본문은 await 지점이 없어(asyncio.sleep(600)에 닿기 전까지) 한
    # 이벤트 루프 틱 안에서 전부 동기 실행된다. 짧게 재운 뒤 취소하면
    # 정확히 "한 번의 반복"만 관측할 수 있다.
    task = asyncio.create_task(cleanup.cleanup_expired_files_loop())
    await asyncio.sleep(0.2)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # text_storage 검증
    assert "expired" not in state.text_storage
    assert "fresh" in state.text_storage

    # jobs 검증 + 딸린 파일 삭제 검증
    assert "expired_job" not in state.jobs
    assert "fresh_job" in state.jobs
    assert not expired_audio.exists()

    # shared 검증 (과거 never_expire 메타데이터도 보관 우회에 쓰이면 안 된다)
    assert not (shared_dir / "expired_share").exists()
    assert (shared_dir / "fresh_share").exists()
    assert not (shared_dir / "legacy_never_expire_share").exists()

    # job_audio 고아 파일 검증
    assert not orphan_old.exists()
    assert orphan_new.exists()


@pytest.mark.asyncio
async def test_cleanup_drops_expired_rate_buckets(tmp_path, monkeypatch):
    """요청 제한 버킷은 IP마다 생기고 지워지는 자리가 없었다.

    프로세스가 살아 있는 내내 자라기만 하는 유일한 인메모리 상태였다 —
    text_storage/jobs/공유파일/고아오디오는 모두 정리 대상인데 이것만 빠져
    있었다. 아직 윈도 안에 있는 기록까지 지우면 제한이 헐거워지므로,
    지난 것만 지우는지도 함께 본다.
    """
    monkeypatch.setattr(cleanup, "SHARED_DIR", str(tmp_path / "shared"))
    monkeypatch.setattr(cleanup, "JOB_AUDIO_DIR", str(tmp_path / "job_audio"))
    now = time.time()

    state._rate_buckets[("synthesize", "1.1.1.1")] = [now - state.RATE_BUCKET_MAX_WINDOW_SEC - 1]
    state._rate_buckets[("synthesize", "2.2.2.2")] = [now]
    state._rate_buckets[("product_event", "3.3.3.3")] = []

    task = asyncio.create_task(cleanup.cleanup_expired_files_loop())
    await asyncio.sleep(0.2)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert ("synthesize", "1.1.1.1") not in state._rate_buckets
    assert ("product_event", "3.3.3.3") not in state._rate_buckets
    assert ("synthesize", "2.2.2.2") in state._rate_buckets
