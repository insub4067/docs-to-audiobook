import os
import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from main import synthesize_document, synthesize_chunk, process_synthesis_task

@pytest.mark.asyncio
async def test_synthesize_chunk_success():
    # We want to mock edge_tts.Communicate so it doesn't actually synthesize anything
    with patch('main.edge_tts.Communicate') as MockCommunicate:
        mock_instance = MagicMock()
        
        async def mock_stream():
            yield {"type": "audio", "data": b"fake_audio_data"}
            yield {"type": "SentenceBoundary"}
            
        mock_instance.stream.return_value = mock_stream()
        MockCommunicate.return_value = mock_instance
        
        idx, audio, _ = await synthesize_chunk(0, "Test chunk", "ko-KR-SunHiNeural", "1.0", "0.0", max_attempts=1)
        
        assert idx == 0
        assert audio == b"fake_audio_data"

@pytest.mark.asyncio
async def test_synthesize_chunk_failure():
    # If the TTS engine raises an exception, we want to see if it retries and fails
    with patch('main.edge_tts.Communicate') as MockCommunicate:
        mock_instance = MagicMock()
        mock_instance.stream.side_effect = Exception("TTS failed")
        MockCommunicate.return_value = mock_instance
        
        with pytest.raises(Exception) as exc_info:
            await synthesize_chunk(0, "Test chunk", "ko-KR-SunHiNeural", "1.0", "0.0", max_attempts=1)

        assert "TTS failed" in str(exc_info.value)


@pytest.mark.asyncio
async def test_synthesize_document_splits_orders_and_offsets():
    """synthesize_document는 이전에 커버리지 0%였던 핵심 로직이다:
    긴 문서를 여러 청크로 쪼개 asyncio.gather로 동시 처리하고, 결과를
    인덱스 순서대로 정렬한 뒤, 문장 타임스탬프를 청크별로 누적 오프셋한다.

    synthesize_chunk 자체는 이미 별도로 테스트하므로 여기서는 patch해
    실제 TTS 없이 이 상위 로직(분할/정렬/오프셋 누적/헤딩 매칭)만 검증한다.
    """
    calls = []

    async def fake_synthesize_chunk(idx, text_chunk, voice, rate, pitch, max_attempts=3):
        calls.append(idx)
        # 청크마다 서로 다른 오디오 바이트를 줘서 순서가 뒤집히면 바로 티가 나게 한다
        audio = f"chunk{idx}".encode()
        if idx == 0:
            sentences = [{"text": "챕터 1", "start": 0, "end": 500}]
        else:
            sentences = [{"text": "다음 내용", "start": 0, "end": 300}]
        return idx, audio, sentences

    # 실제 청크 분할 로직(800자 기준)이 최소 2개 청크를 만들도록 충분히 긴
    # 두 문단을 준다. 정확한 청크 개수는 토크나이저 세부 규칙에 좌우되므로
    # "2개 이상"만 요구해 분할 경계 변화에 취약하지 않게 한다.
    raw_text = "# 챕터 1\n\n" + ("가" * 500 + ". ") + ("나" * 500 + ". ")

    with patch("main.synthesize_chunk", side_effect=fake_synthesize_chunk):
        combined_audio, annotated_sentences, heading_index = await synthesize_document(
            raw_text, "voice", "+0%", "+0Hz"
        )

    assert len(calls) >= 2, "긴 문서가 청크 하나로만 처리됐다(분할 로직 회귀 가능성)"

    # 순서 보존: gather는 완료 순서가 뒤섞일 수 있어 결과를 인덱스로 재정렬한다.
    # combined_audio가 chunk0, chunk1, ... 순서 그대로 이어붙었는지 확인한다.
    expected_audio = b"".join(f"chunk{i}".encode() for i in range(len(calls)))
    assert combined_audio == expected_audio

    # 오프셋 누적: 두 번째 청크의 문장 시작 시각은 0이 아니라 첫 청크의
    # 최대 종료 시각(500ms)만큼 밀려 있어야 한다.
    assert annotated_sentences[0]["start"] == 0
    assert annotated_sentences[1]["start"] == 500

    # 헤딩 매칭: raw_text의 "# 챕터 1"이 첫 문장 "챕터 1"과 매칭되어
    # heading_index에 올라가야 한다.
    assert len(heading_index) == 1
    assert heading_index[0]["text"] == "챕터 1"
    assert heading_index[0]["sentIndex"] == 0
    assert heading_index[0]["startMs"] == 0


@pytest.mark.asyncio
async def test_synthesize_document_chunk_failure_propagates():
    # 청크 하나가 재시도 끝에 완전히 실패하면 asyncio.gather가 예외를
    # 전파해 문서 전체 합성이 실패해야 한다(부분 성공으로 조용히 넘어가면
    # 안 된다).
    async def failing_chunk(idx, text_chunk, voice, rate, pitch, max_attempts=3):
        raise RuntimeError("네트워크 끊김")

    with patch("main.synthesize_chunk", side_effect=failing_chunk):
        with pytest.raises(RuntimeError, match="네트워크 끊김"):
            await synthesize_document("어느 정도 긴 텍스트입니다. " * 5, "voice", "+0%", "+0Hz")


@pytest.mark.asyncio
async def test_synthesize_document_reports_completed_chunks():
    async def fake_synthesize_chunk(idx, text_chunk, voice, rate, pitch, max_attempts=3):
        return idx, b"audio", [{"text": f"문장 {idx}", "start": 0, "end": 100}]

    progress_updates = []
    raw_text = ("가" * 500 + ". ") + ("나" * 500 + ". ")

    with patch("main.synthesize_chunk", side_effect=fake_synthesize_chunk):
        await synthesize_document(
            raw_text,
            "voice",
            "+0%",
            "+0Hz",
            progress_callback=lambda completed, total: progress_updates.append((completed, total)),
        )

    assert progress_updates == [(1, 2), (2, 2)]


@pytest.mark.asyncio
async def test_synthesize_document_to_file_limits_workers_and_preserves_order(tmp_path):
    import main

    active_workers = 0
    max_active_workers = 0

    async def fake_synthesize_chunk(idx, text_chunk, voice, rate, pitch, max_attempts=3):
        nonlocal active_workers, max_active_workers
        active_workers += 1
        max_active_workers = max(max_active_workers, active_workers)
        await asyncio.sleep(0.01)
        active_workers -= 1
        return idx, str(idx).encode(), [{"text": f"문장 {idx}", "start": 0, "end": 100}]

    raw_text = ". ".join(chr(0xAC00 + i) * 800 for i in range(6))
    output_path = tmp_path / "book.mp3"

    with patch("main.synthesize_chunk", side_effect=fake_synthesize_chunk):
        sentences, _, _ = await main.synthesize_document_to_file(
            raw_text, "voice", "+0%", "+0Hz", str(output_path)
        )

    assert output_path.read_bytes() == b"012345"
    assert max_active_workers == 5
    assert [sentence["start"] for sentence in sentences] == [0, 100, 200, 300, 400, 500]


@pytest.mark.asyncio
async def test_process_synthesis_task_success(tmp_path, monkeypatch):
    monkeypatch.setattr("main.JOB_AUDIO_DIR", str(tmp_path))
    from main import jobs

    job_id = "job-success"
    jobs[job_id] = {"status": "processing", "audio_path": None, "sentences": [], "headings": [], "error": None}

    fake_sentences = [{"text": "안녕", "start": 0, "end": 100, "type": "text"}]
    fake_headings = [{"text": "제목", "level": 1, "sentIndex": 0, "startMs": 0}]

    async def fake_synthesize_to_file(raw_text, voice, rate, pitch, output_path, progress_callback=None):
        with open(output_path, "wb") as f:
            f.write(b"audio-bytes")
        return fake_sentences, fake_headings, "# 제목"

    with patch("main.synthesize_document_to_file", side_effect=fake_synthesize_to_file):
        await process_synthesis_task(job_id, "raw text", "voice", "+0%", "+0Hz")

    assert jobs[job_id]["status"] == "completed"
    assert jobs[job_id]["sentences"] == fake_sentences
    assert jobs[job_id]["headings"] == fake_headings
    audio_path = jobs[job_id]["audio_path"]
    assert os.path.exists(audio_path)
    with open(audio_path, "rb") as f:
        assert f.read() == b"audio-bytes"


@pytest.mark.asyncio
async def test_process_synthesis_task_empty_audio_marks_error():
    from main import jobs

    job_id = "job-empty"
    jobs[job_id] = {"status": "processing", "audio_path": None, "sentences": [], "headings": [], "error": None}

    with patch("main.synthesize_document_to_file", new=AsyncMock(return_value=([], [], ""))):
        await process_synthesis_task(job_id, "raw text", "voice", "+0%", "+0Hz")

    assert jobs[job_id]["status"] == "error"
    assert "비어 있습니다" in jobs[job_id]["error"]


@pytest.mark.asyncio
async def test_process_synthesis_task_exception_marks_error():
    from main import jobs

    job_id = "job-exception"
    jobs[job_id] = {"status": "processing", "audio_path": None, "sentences": [], "headings": [], "error": None}

    with patch("main.synthesize_document_to_file", new=AsyncMock(side_effect=RuntimeError("boom"))):
        await process_synthesis_task(job_id, "raw text", "voice", "+0%", "+0Hz")

    assert jobs[job_id]["status"] == "error"
    assert jobs[job_id]["error"] == "boom"
