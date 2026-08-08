"""합성이 끝나기 전에 앞 구간부터 재생에 내주는 경로 테스트.

10만 자 문서는 합성이 다 끝나는 데 70초 넘게 걸린다(실측). 반면 첫 청크는
2초면 나오고 그 하나가 100초 안팎의 오디오다. 그래서 "0번부터 이어지는
구간"만 만들어지는 대로 내주면 사용자가 보는 대기가 70초대에서 2초로 준다.

여기서 지켜야 할 불변조건은 두 가지다.
1. 합쳐진 최종 결과물은 예전과 **바이트 단위로 같다**. 청크 파일로 쪼개
   쓰는 건 내부 구현일 뿐, 오프라인 저장·이어듣기가 그대로여야 한다.
2. 중간이 빈 채로 알리지 않는다. 묶음이 병렬로 도니 3번이 1번보다 먼저
   끝날 수 있는데, 그때 3번을 내주면 순차 재생이 불가능하다.
"""
import asyncio
import os
from unittest.mock import patch

import httpx
import pytest

from main import app
from state import jobs


def _auth_headers(user_id="owner"):
    from auth import create_access_token
    return {"Authorization": f"Bearer {create_access_token({'sub': user_id})}"}


def _chunk_text(count: int) -> str:
    """split_tts_chunks가 정확히 count개로 쪼개도록 800자 이상 단락을 잇는다."""
    return ". ".join(chr(0xAC00 + i) * 800 for i in range(count))


async def _fake_chunk(idx, text_chunk, voice, rate, pitch, max_attempts=3, provider_name=None):
    return idx, f"[{idx}]".encode(), [{"text": f"문장 {idx}", "start": 0, "end": 100}]


@pytest.mark.asyncio
async def test_ready_prefix_only_advances_contiguously(tmp_path):
    """3번이 먼저 끝나도 1·2번이 남아 있으면 알리지 않는다."""
    from routes import tts

    order = [3, 1, 0, 2]
    gates = {i: asyncio.Event() for i in order}

    async def gated_chunk(idx, *args, **kwargs):
        await gates[idx].wait()
        return await _fake_chunk(idx, *args, **kwargs)

    announced = []

    def on_ready(records):
        announced.append([record["index"] for record in records])

    with patch("routes.tts.synthesize_chunk", side_effect=gated_chunk), \
         patch("routes.tts.DOCUMENT_PART_CONCURRENCY", 4):
        task = asyncio.create_task(tts.synthesize_document_to_file(
            _chunk_text(4), "voice", "+0%", "+0Hz", str(tmp_path / "book.mp3"),
            chunk_ready_callback=on_ready,
        ))
        for idx in order:
            gates[idx].set()
            await asyncio.sleep(0.02)
        await task

    # 3 → 아무것도 안 알림, 1 → 여전히 없음, 0 → [0, 1] 한꺼번에, 2 → [2, 3]
    assert announced == [[0, 1], [2, 3]]


@pytest.mark.asyncio
async def test_combined_file_is_unchanged_by_chunking(tmp_path):
    """청크 파일로 쪼개 써도 합본은 예전과 같은 바이트·같은 순서다."""
    from routes import tts

    output = tmp_path / "book.mp3"
    with patch("routes.tts.synthesize_chunk", side_effect=_fake_chunk):
        sentences, _, _ = await tts.synthesize_document_to_file(
            _chunk_text(4), "voice", "+0%", "+0Hz", str(output)
        )

    assert output.read_bytes() == b"[0][1][2][3]"
    assert [sentence["start"] for sentence in sentences] == [0, 100, 200, 300]


@pytest.mark.asyncio
async def test_chunk_files_are_cleaned_up(tmp_path):
    """청크 파일이 남으면 긴 문서마다 디스크가 두 배로 샌다."""
    from routes import tts

    output = tmp_path / "book.mp3"
    with patch("routes.tts.synthesize_chunk", side_effect=_fake_chunk):
        await tts.synthesize_document_to_file(
            _chunk_text(3), "voice", "+0%", "+0Hz", str(output)
        )

    assert sorted(os.listdir(tmp_path)) == ["book.mp3"]


@pytest.mark.asyncio
async def test_chunk_files_are_cleaned_up_on_failure(tmp_path):
    from routes import tts

    async def fails_on_second(idx, *args, **kwargs):
        if idx == 1:
            raise RuntimeError("TTS 실패")
        return await _fake_chunk(idx, *args, **kwargs)

    output = tmp_path / "book.mp3"
    with patch("routes.tts.synthesize_chunk", side_effect=fails_on_second), \
         pytest.raises(RuntimeError):
        await tts.synthesize_document_to_file(
            _chunk_text(3), "voice", "+0%", "+0Hz", str(output)
        )

    assert os.listdir(tmp_path) == []


@pytest.mark.asyncio
async def test_job_serves_ready_chunk_before_completion(tmp_path, monkeypatch):
    """합성 중에도 준비된 청크를 받아 재생할 수 있다."""
    monkeypatch.setattr("routes.tts.JOB_AUDIO_DIR", str(tmp_path))
    job_id = "job-progressive"
    audio_path = tmp_path / f"{job_id}.mp3"
    (tmp_path / f"{job_id}.mp3.chunk-0").write_bytes(b"chunk-zero-audio")
    # ⚠️ 1번 파일도 일부러 만들어 둔다. 파일이 없어서 404가 나면 "준비된
    # 구간까지만 내준다"는 검사를 지워도 테스트가 통과해 버린다(실제로
    # 뮤테이션에서 그렇게 새는 걸 확인했다). 디스크에는 있지만 아직
    # ready_chunks 밖인 상태를 만들어야 그 검사를 실제로 본다.
    (tmp_path / f"{job_id}.mp3.chunk-1").write_bytes(b"chunk-one-not-announced")
    jobs[job_id] = {
        "status": "processing", "user_id": "owner", "ready_chunks": 1,
        "chunk_durations": [1500], "sentences": [{"text": "첫 문장", "start": 0, "end": 900}],
        "completed_chunks": 1, "total_chunks": 9, "audio_path": None,
        "headings": [], "display_markdown": "", "error": None,
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        status = await client.get(f"/api/job/{job_id}", headers=_auth_headers())
        chunk = await client.get(f"/api/job/{job_id}/chunk/0", headers=_auth_headers())
        not_ready = await client.get(f"/api/job/{job_id}/chunk/1", headers=_auth_headers())

    assert status.json()["status"] == "processing"
    assert status.json()["ready_chunks"] == 1
    assert status.json()["sentences"] == [{"text": "첫 문장", "start": 0, "end": 900}]
    assert chunk.status_code == 200
    assert chunk.content == b"chunk-zero-audio"
    # 아직 알리지 않은 구간을 주면, 클라이언트가 순서를 건너뛴 채 재생한다.
    assert not_ready.status_code == 404
    assert not audio_path.exists()  # 합본은 합성이 끝나야 생긴다
    del jobs[job_id]


@pytest.mark.asyncio
async def test_chunk_endpoint_rejects_other_users(tmp_path, monkeypatch):
    monkeypatch.setattr("routes.tts.JOB_AUDIO_DIR", str(tmp_path))
    job_id = "job-private"
    (tmp_path / f"{job_id}.mp3.chunk-0").write_bytes(b"secret")
    jobs[job_id] = {"status": "processing", "user_id": "owner", "ready_chunks": 1}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/job/{job_id}/chunk/0", headers=_auth_headers("someone-else"))

    assert response.status_code == 403
    del jobs[job_id]


def _processing_job(sentences: list[dict]) -> dict:
    return {
        "status": "processing", "user_id": "owner", "ready_chunks": 1,
        "chunk_durations": [1500], "sentences": sentences,
        "completed_chunks": 1, "total_chunks": 9, "audio_path": None,
        "headings": [], "display_markdown": "", "error": None,
    }


SENTENCES = [
    {"text": "첫 문장", "start": 0, "end": 900},
    {"text": "둘째 문장", "start": 900, "end": 1800},
    {"text": "셋째 문장", "start": 1800, "end": 2700},
]


@pytest.mark.asyncio
async def test_status_returns_only_sentences_after_since():
    """예전에는 2초마다 문장 배열 전체를 다시 보냈다. 긴 문서일수록 같은
    데이터를 수백 번 나르므로, 받아 간 지점 뒤만 잘라 준다."""
    job_id = "job-since"
    jobs[job_id] = _processing_job(SENTENCES)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        first = await client.get(f"/api/job/{job_id}", headers=_auth_headers())
        rest = await client.get(f"/api/job/{job_id}?since=2", headers=_auth_headers())
        nothing_new = await client.get(f"/api/job/{job_id}?since=3", headers=_auth_headers())

    # since가 없으면 처음부터 — 예전 클라이언트도 그대로 동작한다.
    assert first.json()["sentences"] == SENTENCES
    assert rest.json()["sentences"] == [SENTENCES[2]]
    assert nothing_new.json()["sentences"] == []
    del jobs[job_id]


@pytest.mark.asyncio
async def test_status_ignores_negative_since():
    """음수를 그대로 슬라이스에 넘기면 뒤에서부터 잘려 엉뚱한 구간이 나간다."""
    job_id = "job-since-negative"
    jobs[job_id] = _processing_job(SENTENCES)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/job/{job_id}?since=-2", headers=_auth_headers())

    assert response.json()["sentences"] == SENTENCES
    del jobs[job_id]


@pytest.mark.asyncio
async def test_completed_status_ignores_since(tmp_path, monkeypatch):
    """⚠️ 완료 응답만은 전체를 보낸다. 합성이 끝나면 서버가 타이밍을 다시 매긴
    배열로 통째로 갈아끼우므로(process_synthesis_task), 여기서 잘라 보내면
    클라이언트가 합성 중에 받아 둔 예전 값을 그대로 들고 있게 된다."""
    monkeypatch.setattr("routes.tts.JOB_AUDIO_DIR", str(tmp_path))
    job_id = "job-since-completed"
    jobs[job_id] = {
        "status": "completed", "user_id": "owner", "sentences": SENTENCES,
        "headings": [], "display_markdown": "", "audio_path": str(tmp_path / "a.mp3"),
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/job/{job_id}?since=2", headers=_auth_headers())

    assert response.json()["sentences"] == SENTENCES
    del jobs[job_id]
