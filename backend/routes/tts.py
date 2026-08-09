"""음성 목록·미리듣기, TTS 합성 엔진, 작업 상태/오디오, 관리자 대용량
백그라운드 합성까지 — 서로 강하게 얽혀 있어(synthesize_text가 백그라운드
경로를 직접 호출하고, 백그라운드 작업이 다시 이 파일의 합성 엔진을 쓴다)
분리하면 순환 참조만 생기므로 한 모듈에 둔다.
"""
import os
import asyncio
import time
import uuid
import logging
import secrets
import shutil
from datetime import datetime, timezone
from fastapi import APIRouter, Request, BackgroundTasks, Form, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask

from state import (
    BASE_DIR, JOB_AUDIO_DIR, jobs, text_storage, MAX_SYNTH_CHARS,
    DOCUMENT_PART_CONCURRENCY, background_synthesis_lock, has_enough_disk_for_synthesis,
    supabase_or_503, upload_audiobook_objects, remove_audiobook_objects,
    resolve_job_owner, require_job_owner,
    enforce_rate_limit, validate_folder_ownership,
)
from text_processing import (
    build_document_representations, extract_markdown_headings,
    annotate_sentences_with_headings, annotate_sentences_with_tables, clean_tts_text,
)
from push_notifications import send_background_job_ready
from tts_providers import get_tts_provider
from tts_providers.voice_catalog import (
    VOICE_CATALOG, DEFAULT_VOICE_KEY, find_voice_key, resolve_voice_key, provider_for_voice,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# 음성 미리듣기. 짧은 한 문장이라 합성이 몇 초면 끝나고, 한 번 만들면
# 디스크에 캐시해 재사용한다. 공급자별로 실제 오디오가 다르므로 파일명에
# 공급자 이름을 넣어 캐시가 섞이지 않게 한다.
VOICE_PREVIEW_TEXT = "안녕하세요. 이 목소리로 문서를 읽어 드릴게요. 오늘도 좋은 하루 보내세요."
VOICE_PREVIEW_DIR = os.path.join(BASE_DIR, "voice_previews")
os.makedirs(VOICE_PREVIEW_DIR, exist_ok=True)
voice_preview_lock = asyncio.Lock()


@router.get("/api/voices")
async def get_voices(tone: str = None, use_case: str = None):
    """음성 목록 반환. tone/use_case로 필터링 가능.

    음성마다 합성 엔진(edge_tts/google)이 고정돼 있어(voice_catalog.py),
    실제 공급자에게 매번 물어볼 필요 없이 카탈로그를 그대로 신뢰한다.
    VOICE_CATALOG의 등록 순서가 곧 노출 순서다(첫 번째가 기본값)."""
    voices = [
        {
            "key": key,
            "name": meta["friendly_name"],
            "gender": meta["gender"],
            "locale": meta["locale"],
            "friendly_name": meta["friendly_name"],
            "description": meta["description"],
            "tone": meta["tone"],
            "use_case": meta["use_case"],
        }
        for key, meta in VOICE_CATALOG.items()
    ]

    if tone:
        voices = [v for v in voices if v.get("tone") == tone]
    if use_case:
        voices = [v for v in voices if use_case in v.get("use_case", [])]

    return voices


@router.get("/api/voices/{voice_key}/preview")
async def get_voice_preview(voice_key: str):
    """음성 미리듣기. 처음 요청될 때 한 번 만들고 디스크에 캐시한다."""
    # 경로에 그대로 들어가므로 반드시 허용 목록으로 검증한다. 예전
    # edge-tts short_name 형식도 함께 받아들이되(캐시된 구버전 프론트
    # 대응), 모르는 값은 거부한다.
    resolved_key = find_voice_key(voice_key)
    if resolved_key is None:
        raise HTTPException(status_code=404, detail="지원하지 않는 음성입니다.")

    provider_name = provider_for_voice(resolved_key)
    path = os.path.join(VOICE_PREVIEW_DIR, f"{provider_name}_{resolved_key}.mp3")
    if not os.path.exists(path):
        async with voice_preview_lock:
            # 락을 기다리는 동안 다른 요청이 이미 만들었을 수 있다
            if not os.path.exists(path):
                try:
                    audio_bytes, _, _ = await synthesize_document(
                        VOICE_PREVIEW_TEXT, resolved_key, "+5%", "+0Hz"
                    )
                    if not audio_bytes:
                        raise RuntimeError("빈 오디오")
                    with open(path, "wb") as f:
                        f.write(audio_bytes)
                except Exception as e:
                    logger.warning("Voice preview generation failed voice=%s: %s", resolved_key, e)
                    raise HTTPException(status_code=503, detail="미리듣기를 만들지 못했습니다.")

    return FileResponse(path, media_type="audio/mpeg")


async def synthesize_chunk(
    chunk_index: int, text_chunk: str, voice: str, rate: str, pitch: str,
    max_attempts: int = 3, provider_name: str | None = None,
):
    # TTS 발음용 깨끗한 텍스트
    tts_text = clean_tts_text(text_chunk)
    if not tts_text:
        tts_text = text_chunk

    # 보통은 음성에 고정된 엔진을 쓴다(voice_catalog.provider_for_voice).
    # provider_name이 명시적으로 오면(기본 제공 오디오북처럼 특정 음성의
    # 고정 엔진과 무관하게 특정 공급자를 강제하고 싶을 때) 그걸 우선한다.
    provider = get_tts_provider(provider_name or provider_for_voice(voice))
    # TTS 공급자는 특정 호스팅 환경에서 개별 연결이 간헐적으로 끊긴다.
    # 청크 단위로 재시도해, 문서 전체를 병렬 변환할 때 청크 하나의 일시적
    # 실패가 전체 asyncio.gather를 실패시키지 않도록 한다.
    last_error = None
    for attempt in range(max_attempts):
        try:
            audio_data, sentences = await provider.synthesize(tts_text, voice, rate, pitch)
            if audio_data:
                return chunk_index, audio_data, sentences
            last_error = RuntimeError("빈 오디오 응답을 받았습니다.")
        except Exception as e:
            last_error = e

        if attempt < max_attempts - 1:
            await asyncio.sleep(1.5 * (attempt + 1))

    raise last_error


def split_tts_chunks(text: str) -> list[str]:
    """Edge TTS에 보낼 800자 안팎의 순서 보장 청크를 만든다."""
    paragraphs = text.split(". ")
    chunks = []
    current_chunk = ""

    for paragraph in paragraphs:
        if len(current_chunk) + len(paragraph) < 800:
            current_chunk += paragraph + ". "
        else:
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            current_chunk = paragraph + ". "
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    return chunks or [text]

async def synthesize_document(
    raw_text: str, voice: str, rate: str, pitch: str, progress_callback=None, provider_name: str | None = None,
) -> tuple:
    """Synthesize a full document into (audio_bytes, annotated_sentences, heading_index)."""
    display_markdown, text, tables = build_document_representations(raw_text)
    headings = extract_markdown_headings(display_markdown)

    chunks = split_tts_chunks(text)

    completed_chunks = 0

    async def synthesize_with_progress(chunk_index: int, chunk: str):
        nonlocal completed_chunks
        result = await synthesize_chunk(chunk_index, chunk, voice, rate, pitch, provider_name=provider_name)
        completed_chunks += 1
        if progress_callback:
            progress_callback(completed_chunks, len(chunks))
        return result

    # Process all chunks concurrently using asyncio.gather
    tasks = [
        synthesize_with_progress(i, chunk)
        for i, chunk in enumerate(chunks)
    ]
    results = await asyncio.gather(*tasks)

    # Sort by chunk index to maintain exact order
    results.sort(key=lambda x: x[0])

    # 청크를 += 로 이어붙이면 매번 전체 복사본이 생겨 피크 메모리가 2배가 된다.
    # 30,000자 문서 기준 50.8MB -> 25.8MB.
    audio_parts = []
    combined_sentences = []
    current_time_offset = 0

    for idx, audio_data, sentences in results:
        audio_parts.append(audio_data)

        chunk_duration = 0
        for s in sentences:
            combined_sentences.append({
                "text": s["text"],
                "start": s["start"] + current_time_offset,
                "end": s["end"] + current_time_offset
            })
            if s["end"] > chunk_duration:
                chunk_duration = s["end"]

        # Offset next chunk sentences by duration of current chunk
        current_time_offset += chunk_duration

    combined_audio = b"".join(audio_parts)
    # 합친 뒤에는 조각과 gather 결과가 필요 없다. 참조를 끊어 즉시 회수시킨다.
    audio_parts.clear()
    results.clear()

    # Annotate sentences with heading metadata
    annotated_sentences, heading_index = annotate_sentences_with_headings(
        combined_sentences, headings
    )
    annotate_sentences_with_tables(annotated_sentences, tables)

    return combined_audio, annotated_sentences, heading_index


def chunk_audio_path(output_path: str, chunk_index: int) -> str:
    return f"{output_path}.chunk-{chunk_index}"


async def synthesize_document_to_file(
    raw_text: str,
    voice: str,
    rate: str,
    pitch: str,
    output_path: str,
    progress_callback=None,
    provider_name: str | None = None,
    chunk_ready_callback=None,
) -> tuple[list, list, str]:
    """긴 문서를 최대 다섯 묶음으로 병렬 합성해 MP3를 디스크에 기록한다.

    청크마다 **개별 파일**로 먼저 쓰고 마지막에 순서대로 합친다. 예전에는
    묶음(part)당 한 파일에 이어 붙였는데, 그러면 묶음이 통째로 끝나기 전에는
    아무것도 꺼내 쓸 수 없었다. 청크 파일로 두면 앞에서부터 준비되는 대로
    재생에 내줄 수 있다 — 10만 자 문서에서 사용자가 보는 대기가 70초대에서
    첫 청크 2초로 줄어든다(청크 하나가 100초 안팎 분량이고 합성은 1초당
    27초 분량을 만들어서, 재생이 합성을 따라잡지 않는다).

    합쳐진 결과물은 예전과 바이트 단위로 같다. 묶음 파일도 청크를 순서대로
    담았고 묶음을 순서대로 이었으므로, 청크를 0..N-1로 잇는 것과 동일하다.

    chunk_ready_callback(records)는 "0번부터 끊김 없이 이어지는 구간"이
    늘어날 때만 부른다. 중간이 비면 순차 재생을 못 하므로 개별 청크가
    끝났다는 사실만으로는 알릴 의미가 없다.
    """
    display_markdown, text, tables = build_document_representations(raw_text)
    headings = extract_markdown_headings(display_markdown)
    chunks = split_tts_chunks(text)
    part_count = min(DOCUMENT_PART_CONCURRENCY, len(chunks))
    base_part_size, extra_chunks = divmod(len(chunks), part_count)
    parts = []
    start = 0
    for part_index in range(part_count):
        part_size = base_part_size + (1 if part_index < extra_chunks else 0)
        parts.append(list(enumerate(chunks[start:start + part_size], start)))
        start += part_size
    chunk_paths = [chunk_audio_path(output_path, index) for index in range(len(chunks))]
    completed_chunks = 0
    # 끝난 자리만 채워진다. 묶음이 병렬로 도니 중간이 비어 있을 수 있다.
    chunk_results: list[dict | None] = [None] * len(chunks)
    ready_count = 0
    # 이미 알린 구간의 총 길이. 매번 0..ready_count를 다시 더하면 청크 수의
    # 제곱에 비례한다 — 관리자 상한(5천만 자 = 6만 청크)에서는 합성보다
    # 이 합산이 더 오래 걸린다.
    ready_offset = 0

    def advance_ready_prefix():
        """0번부터 연속으로 끝난 구간이 늘었으면 그만큼만 알린다."""
        nonlocal ready_count, ready_offset
        newly = []
        offset = ready_offset
        while ready_count < len(chunks) and chunk_results[ready_count] is not None:
            record = chunk_results[ready_count]
            newly.append({
                "index": ready_count,
                "duration": record["duration"],
                "sentences": [
                    {"text": s["text"], "start": s["start"] + offset, "end": s["end"] + offset}
                    for s in record["sentences"]
                ],
            })
            offset += record["duration"]
            ready_count += 1
        ready_offset = offset
        if newly and chunk_ready_callback:
            chunk_ready_callback(newly)

    async def synthesize_part(part_index: int, part: list[tuple[int, str]]):
        nonlocal completed_chunks
        for chunk_index, chunk in part:
            _, audio_data, sentences = await synthesize_chunk(
                chunk_index, chunk, voice, rate, pitch, provider_name=provider_name
            )
            with open(chunk_paths[chunk_index], "wb") as audio_file:
                audio_file.write(audio_data)
            chunk_results[chunk_index] = {
                "sentences": [dict(sentence) for sentence in sentences],
                "duration": max((sentence["end"] for sentence in sentences), default=0),
            }
            completed_chunks += 1
            if progress_callback:
                progress_callback(completed_chunks, len(chunks))
            advance_ready_prefix()

    try:
        await asyncio.gather(*[
            synthesize_part(part_index, part)
            for part_index, part in enumerate(parts)
        ])

        combined_sentences = []
        current_offset = 0
        with open(output_path, "wb") as output_file:
            for chunk_index in range(len(chunks)):
                with open(chunk_paths[chunk_index], "rb") as chunk_file:
                    shutil.copyfileobj(chunk_file, output_file)
                record = chunk_results[chunk_index]
                for sentence in record["sentences"]:
                    combined_sentences.append({
                        "text": sentence["text"],
                        "start": sentence["start"] + current_offset,
                        "end": sentence["end"] + current_offset,
                    })
                current_offset += record["duration"]
    except Exception:
        try:
            os.remove(output_path)
        except OSError:
            pass
        raise
    finally:
        for chunk_path in chunk_paths:
            try:
                os.remove(chunk_path)
            except OSError:
                pass

    annotated_sentences, heading_index = annotate_sentences_with_headings(combined_sentences, headings)
    annotate_sentences_with_tables(annotated_sentences, tables)
    return annotated_sentences, heading_index, display_markdown


def _record_synthesis_usage(job_id: str, raw_text: str, voice: str, elapsed: float, succeeded: bool) -> None:
    """사용자 한 명이 실제로 얼마의 TTS 비용을 만드는지 알기 위한 원자료.

    추정 단가가 아니라 원단위(문자 수)만 남긴다 — 단가는 바뀌고 provider마다
    다르므로, 계산은 조회 시점에 한다.

    실패한 합성도 남긴다. 문자는 이미 소모됐으므로 빼고 세면 실비용을
    과소평가한다(특히 Edge TTS는 호스트에 따라 간헐적으로 실패한다).

    기록 실패가 합성을 망치면 안 된다 — 지표는 부수적이고 오디오가 본체다.
    """
    job = jobs.get(job_id, {})
    audio_ms = sum(job.get("chunk_durations", []))
    try:
        supabase_or_503().table("synthesis_usage").insert({
            "user_id": job.get("user_id"),
            "provider": provider_for_voice(voice),
            "voice": voice,
            "characters": len(raw_text),
            "audio_seconds": round(audio_ms / 1000, 2) if audio_ms else None,
            "elapsed_seconds": round(elapsed, 2),
            "succeeded": succeeded,
        }).execute()
    except Exception as e:
        logger.warning("[synthesis-usage] 기록 실패: %s", e)


async def process_synthesis_task(job_id: str, raw_text: str, voice: str, rate: str, pitch: str):
    started_at = time.monotonic()
    try:
        def update_progress(completed_chunks: int, total_chunks: int):
            jobs[job_id]["completed_chunks"] = completed_chunks
            jobs[job_id]["total_chunks"] = total_chunks

        def publish_ready_chunks(records: list[dict]):
            """앞에서부터 이어지는 구간이 늘 때마다 재생에 필요한 것만 채운다.

            문장은 여기서도 누적해 둔다 — 클라이언트가 첫 청크를 트는 순간
            이미 그 구간의 하이라이트가 맞아야 하기 때문이다."""
            job = jobs.get(job_id)
            if job is None:
                return
            # += 가 아니라 extend인 이유: 리스트를 새로 만들면 청크가 끝날
            # 때마다 지금까지의 문장 전체가 복사된다. 청크 수의 제곱에
            # 비례하는 복사라, 문서가 길수록 급격히 나빠진다.
            job["sentences"].extend(
                sentence for record in records for sentence in record["sentences"]
            )
            job["chunk_durations"].extend(record["duration"] for record in records)
            job["ready_chunks"] = records[-1]["index"] + 1

        audio_path = os.path.join(JOB_AUDIO_DIR, f"{job_id}.mp3")
        annotated_sentences, heading_index, display_markdown = await synthesize_document_to_file(
            raw_text, voice, rate, pitch, audio_path,
            progress_callback=update_progress,
            chunk_ready_callback=publish_ready_chunks,
        )

        if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = "음성 합성 결과가 비어 있습니다."
            _record_synthesis_usage(job_id, raw_text, voice, time.monotonic() - started_at, succeeded=False)
            return

        jobs[job_id]["audio_path"] = audio_path
        jobs[job_id]["sentences"] = annotated_sentences
        jobs[job_id]["headings"] = heading_index
        jobs[job_id]["display_markdown"] = display_markdown
        jobs[job_id]["status"] = "completed"
        _record_synthesis_usage(job_id, raw_text, voice, time.monotonic() - started_at, succeeded=True)

    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)
        _record_synthesis_usage(job_id, raw_text, voice, time.monotonic() - started_at, succeeded=False)


def _store_background_audiobook(user_id: str, title: str, job: dict, folder_id: str | None = None) -> str:
    """브라우저가 없어도 서버가 완성본을 사용자 보관함에 저장한다.

    Storage 업로드를 모두 마친 뒤에야 DB 행을 만든다 — 순서를 반대로 하면
    업로드가 중간에 실패했을 때 파일 없는 audiobooks 행이 고아로 남는다.
    """
    supabase = supabase_or_503()
    audiobook_id = str(uuid.uuid4())

    with open(job["audio_path"], "rb") as audio_file:
        audio_path = upload_audiobook_objects(
            supabase, user_id, audiobook_id, audio_file, job["sentences"]
        )

    try:
        if folder_id:
            # 작업을 큐에 올릴 때는 폴더 소유권을 확인했지만, 몇 시간짜리
            # 작업이 끝나기 전에 그 폴더가 삭제됐을 수 있다 — 그 경우 오류로
            # 날리지 말고 루트에 저장한다.
            found = supabase.table("folders").select("id") \
                .eq("id", folder_id).eq("user_id", user_id).execute().data
            if not found:
                folder_id = None

        supabase.table("audiobooks").insert({
            "id": audiobook_id,
            "user_id": user_id,
            "title": title[:255],
            "file_name": title[:255],
            "storage_path": audio_path,
            "folder_id": folder_id,
        }).execute()
    except Exception:
        # 행이 없으면 방금 올린 두 파일을 가리키는 것이 아무것도 없다 —
        # 버킷에만 남아 영영 지워지지 않는다.
        remove_audiobook_objects(supabase, user_id, audiobook_id)
        raise
    return audiobook_id


def _fresh_job_state(user_id: str) -> dict:
    """새로 시작하거나(첫 시도·재개·재시도) 다시 시작하는 작업의 초기 상태.
    이 모양을 쓰는 세 곳(최초 시작, 재시작 후 재개, 전체 재시도)이 서로
    어긋나지 않게 한 곳에 모은다."""
    return {
        "status": "processing",
        "audio_path": None,
        "sentences": [],
        "headings": [],
        "display_markdown": "",
        "completed_chunks": 0,
        "total_chunks": 0,
        # 0번부터 끊김 없이 준비된 청크 수. 클라이언트는 합성이 끝나기 전에도
        # 0..ready_chunks-1을 순서대로 재생한다.
        "ready_chunks": 0,
        "chunk_durations": [],
        "error": None,
        "created_at": time.time(),
        "user_id": user_id,
    }


async def process_background_synthesis_task(job_id: str, user_id: str, title: str, raw_text: str, voice: str, rate: str, pitch: str, folder_id: str | None = None):
    """청크 단위 재시도로도 못 살린 실패는 문서 전체를 처음부터 다시 돌린다.

    몇 시간짜리 관리자 작업이 청크 하나의 일시적 오류 때문에 통째로
    날아가는 게 부분 재시도 인프라를 만드는 것보다 더 나쁘다고 판단해,
    "전체 성공 아니면 처음부터 다시"(all or nothing)로 간다 — 이미
    background_tasks로 돌아가는 fire-and-forget 작업이라 몇 번 더
    돌리는 비용은 낮고, 원문은 완료 전까지 DB에 그대로 있어 재시도가
    항상 안전하다.
    """
    supabase = supabase_or_503()
    max_job_attempts = 3
    last_error = "음성 합성에 실패했습니다."

    for attempt in range(1, max_job_attempts + 1):
        try:
            await asyncio.to_thread(
                lambda: supabase.table("background_synthesis_jobs").update({"status": "processing"}).eq("id", job_id).execute()
            )
            jobs[job_id] = _fresh_job_state(user_id)
            await process_synthesis_task(job_id, raw_text, voice, rate, pitch)
            job = jobs.get(job_id, {})
            if job.get("status") == "completed":
                audiobook_id = await asyncio.to_thread(_store_background_audiobook, user_id, title, job, folder_id)
                await asyncio.to_thread(
                    lambda: supabase.table("background_synthesis_jobs").update({
                        "status": "completed",
                        "source_text": None,
                        "audiobook_id": audiobook_id,
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                    }).eq("id", job_id).execute()
                )
                try:
                    await asyncio.to_thread(send_background_job_ready, user_id, job_id)
                except Exception as error:
                    logger.warning("Background completion push failed error_type=%s", type(error).__name__)
                return
            last_error = job.get("error") or last_error
        except Exception as e:
            last_error = str(e)

        if attempt < max_job_attempts:
            await asyncio.sleep(30 * attempt)

    jobs.setdefault(job_id, {})["status"] = "error"
    jobs[job_id]["error"] = last_error
    await asyncio.to_thread(
        lambda: supabase.table("background_synthesis_jobs").update({"status": "error", "error": last_error}).eq("id", job_id).execute()
    )


@router.post("/api/synthesize")
async def synthesize_text(
    request: Request,
    background_tasks: BackgroundTasks,
    text_id: str = Form(...),
    text_access_token: str = Form(""),
    voice: str = Form(DEFAULT_VOICE_KEY),
    rate: str = Form("+5%"),
    pitch: str = Form("+0Hz"),
    folder_id: str = Form(None),
    authorization: str = Header(None),
    anonymous_session: str = Header(None, alias="X-Anonymous-Session")
):
    # voice_key든 예전 edge-tts short_name(캐시된 구버전 프론트)이든 여기서
    # 한 번에 정규화한다 — 이후로는 항상 voice_key만 흐른다.
    voice = resolve_voice_key(voice)
    user_id = resolve_job_owner(authorization, anonymous_session)
    # 가장 비싼 엔드포인트다. 배치 8개를 여러 번 돌릴 여유는 남긴다.
    enforce_rate_limit(request, "synthesize", limit=40, window_sec=600)

    if text_id not in text_storage:
        raise HTTPException(status_code=404, detail="요청한 텍스트 데이터를 찾을 수 없거나 만료되었습니다.")

    data = text_storage[text_id]
    if not secrets.compare_digest(data.get("access_token", ""), text_access_token):
        raise HTTPException(status_code=403, detail="이 문서를 변환할 권한이 없습니다.")
    raw_text = data["text"]

    max_synth_chars = data.get("max_synth_chars", MAX_SYNTH_CHARS)
    if len(raw_text) > max_synth_chars:
        raise HTTPException(
            status_code=413,
            detail=f"문서가 너무 깁니다. 최대 {max_synth_chars:,}자까지 변환할 수 있습니다 "
                   f"(현재 {len(raw_text):,}자)."
        )

    def _new_job_id_and_state() -> str:
        job_id = str(uuid.uuid4())
        jobs[job_id] = _fresh_job_state(user_id)
        return job_id

    if max_synth_chars > MAX_SYNTH_CHARS:
        # 대용량 작업은 브라우저의 폴링·클라우드 업로드에 의존하지 않는다.
        # 완료 후 서버가 직접 보관함에 저장하므로 앱을 닫아도 결과가 남는다.
        if not authorization:
            raise HTTPException(status_code=401, detail="대용량 문서는 로그인 후 변환할 수 있습니다.")

        supabase = supabase_or_503()
        if folder_id:
            validate_folder_ownership(supabase, user_id, folder_id)
        async with background_synthesis_lock:
            # 업로드 단계의 락과 별개다. 실제 CPU를 오래 쓰는 건 합성이므로,
            # 이미 진행 중인 대용량 작업이 있으면 새 작업을 거부한다. 확인과
            # 큐 등록을 같은 락 안에서 해 경합으로 두 개가 동시에 뚫리지 않게 한다.
            existing = await asyncio.to_thread(
                lambda: supabase.table("background_synthesis_jobs").select("id")
                .in_("status", ["queued", "processing"]).limit(1).execute().data or []
            )
            if existing:
                raise HTTPException(
                    status_code=429,
                    detail="이미 진행 중인 대용량 작업이 있습니다. 완료 후 다시 시도해 주세요.",
                )

            if not has_enough_disk_for_synthesis(len(raw_text)):
                raise HTTPException(
                    status_code=413,
                    detail="지금 서버 디스크 여유가 부족해 이 문서를 처리할 수 없습니다. "
                           "다른 작업이 끝난 뒤 다시 시도해 주세요.",
                )

            job_id = _new_job_id_and_state()
            await asyncio.to_thread(
                lambda: supabase.table("background_synthesis_jobs").insert({
                    "id": job_id,
                    "user_id": user_id,
                    "source_text": raw_text,
                    "title": data["filename"],
                    "voice": voice,
                    "rate": rate,
                    "pitch": pitch,
                    "folder_id": folder_id,
                }).execute()
            )
        background_tasks.add_task(
            process_background_synthesis_task,
            job_id,
            user_id,
            data["filename"],
            raw_text,
            voice,
            rate,
            pitch,
            folder_id,
        )
        return {"job_id": job_id, "background_started": True}

    job_id = _new_job_id_and_state()
    background_tasks.add_task(process_synthesis_task, job_id, raw_text, voice, rate, pitch)
    return {"job_id": job_id}

@router.get("/api/job/{job_id}")
async def get_job_status(
    job_id: str,
    since: int = 0,
    authorization: str = Header(None),
    anonymous_session: str = Header(None, alias="X-Anonymous-Session")
):
    """since는 클라이언트가 이미 받아 둔 문장 수다. 합성 중에는 그 뒤로 늘어난
    것만 돌려준다 — 예전에는 2초마다 문장 배열 전체를 다시 보내서, 긴 문서일수록
    같은 데이터를 수백 번 반복 전송했다."""
    job = require_job_owner(job_id, authorization, anonymous_session)

    if job["status"] == "completed":
        # 오디오는 별도 엔드포인트에서 파일로 스트리밍한다. 여기서는
        # 메타데이터만 주고 job은 남겨둔다(오디오를 받아가야 정리된다).
        #
        # 완료 응답만 문장 전체를 싣는다. 합성이 끝나면 타이밍을 다시 매긴
        # annotated_sentences로 통째로 갈아끼우기 때문에(process_synthesis_task),
        # 여기서 잘라 보내면 클라이언트가 합성 중에 받아 둔 예전 값을 그대로
        # 들고 있게 된다. 한 번만 나가는 응답이라 전체를 보내도 낭비가 아니다.
        return JSONResponse(content={
            "status": "completed",
            "audio_url": f"/api/job/{job_id}/audio",
            "sentences": job["sentences"],
            "headings": job.get("headings", []),
            "display_markdown": job.get("display_markdown", ""),
        })

    # 아직 합성 중이어도 앞에서부터 준비된 청크는 바로 들려줄 수 있다.
    # ready_chunks는 "0번부터 끊김 없이 이어지는" 개수라, 클라이언트는
    # 0..ready_chunks-1을 순서대로 재생하면 된다.
    return JSONResponse(content={
        "status": job["status"],
        "error": job.get("error"),
        "completed_chunks": job.get("completed_chunks", 0),
        "total_chunks": job.get("total_chunks", 0),
        "ready_chunks": job.get("ready_chunks", 0),
        "chunk_durations": job.get("chunk_durations", []),
        # 합성 중 문장은 앞에서부터 쌓이기만 한다(publish_ready_chunks). 그래서
        # 받아 간 지점부터 잘라 보내도 클라이언트가 이어붙이면 원본과 같아진다.
        "sentences": job.get("sentences", [])[max(since, 0):],
        "headings": job.get("headings", []),
        "display_markdown": job.get("display_markdown", ""),
    })


@router.get("/api/job/{job_id}/chunk/{chunk_index}")
async def get_job_chunk(
    job_id: str,
    chunk_index: int,
    authorization: str = Header(None),
    anonymous_session: str = Header(None, alias="X-Anonymous-Session")
):
    """합성이 끝나기 전에도 준비된 청크를 하나씩 내려준다.

    ⚠️ 합성이 완료되면 청크 파일은 지워지고 합본 하나만 남는다. 그래서
    마지막 청크를 받는 도중에 완료되면 404가 날 수 있다. 클라이언트는
    이때 /api/job/{id}/audio(합본)로 갈아타야 한다 — 상태가 completed면
    청크를 더 요청하지 않는 것이 정상 경로다.
    """
    job = require_job_owner(job_id, authorization, anonymous_session)
    if chunk_index < 0 or chunk_index >= job.get("ready_chunks", 0):
        raise HTTPException(status_code=404, detail="아직 준비되지 않은 구간입니다.")

    audio_path = job.get("audio_path") or os.path.join(JOB_AUDIO_DIR, f"{job_id}.mp3")
    chunk_path = chunk_audio_path(audio_path, chunk_index)
    if not os.path.exists(chunk_path):
        raise HTTPException(status_code=404, detail="이 구간은 이미 합본으로 합쳐졌습니다.")

    return FileResponse(chunk_path, media_type="audio/mpeg")


@router.get("/api/job/{job_id}/audio")
async def get_job_audio(
    job_id: str,
    authorization: str = Header(None),
    anonymous_session: str = Header(None, alias="X-Anonymous-Session")
):
    job = require_job_owner(job_id, authorization, anonymous_session)
    if job.get("status") != "completed":
        raise HTTPException(status_code=404, detail="해당 작업의 오디오를 찾을 수 없습니다.")

    audio_path = job.get("audio_path")
    if not audio_path or not os.path.exists(audio_path):
        raise HTTPException(status_code=404, detail="오디오 파일이 만료되었습니다.")

    # 전송이 끝난 뒤에 파일과 job 항목을 정리한다
    def _cleanup():
        try:
            os.remove(audio_path)
        except OSError:
            pass
        jobs.pop(job_id, None)

    return FileResponse(
        audio_path,
        media_type="audio/mpeg",
        background=BackgroundTask(_cleanup)
    )


async def resume_background_synthesis_jobs():
    """배포·재시작 중 끊긴 대용량 작업을 원문으로 다시 시작한다."""
    try:
        supabase = supabase_or_503()
        rows = await asyncio.to_thread(
            lambda: supabase.table("background_synthesis_jobs").select("*")
            .in_("status", ["queued", "processing"]).execute().data or []
        )
        for row in rows:
            if not row.get("source_text"):
                continue
            job_id = row["id"]

            # 조건부로 상태를 선점한다. 배포 중 이전·새 프로세스가 잠깐
            # 겹치는 것처럼 두 재개 시도가 같은 행을 동시에 집어가도,
            # DB가 원자적으로 처리해 update가 실제로 걸린 쪽만 진행한다.
            # 이게 없으면 같은 작업이 두 번 처음부터 합성되고, 완료 시
            # audiobooks 행도 중복으로 만들어질 수 있다.
            claimed = await asyncio.to_thread(
                lambda status=row["status"]: supabase.table("background_synthesis_jobs")
                .update({"status": "processing"})
                .eq("id", job_id).eq("status", status).execute().data or []
            )
            if not claimed:
                continue

            jobs[job_id] = _fresh_job_state(row["user_id"])
            # 이 배포 이전에 큐에 들어간 행은 voice 컬럼에 예전 edge-tts
            # short_name이 그대로 남아있을 수 있다 — voice_key로 정규화한다.
            asyncio.create_task(process_background_synthesis_task(
                job_id, row["user_id"], row["title"], row["source_text"],
                resolve_voice_key(row["voice"]), row["rate"], row["pitch"],
                row.get("folder_id"),
            ))
    except Exception as e:
        logger.exception("Background job resume failed: %s", e)


@router.get("/api/audio/{job_id}.mp3")
async def download_audiobook(
    job_id: str,
    authorization: str = Header(None),
    anonymous_session: str = Header(None, alias="X-Anonymous-Session")
):
    job = require_job_owner(job_id, authorization, anonymous_session)
    audio_path = job.get("audio_path")
    if not audio_path or not os.path.exists(audio_path):
        raise HTTPException(status_code=404, detail="Audio file not found")

    return FileResponse(audio_path, media_type="audio/mpeg")
