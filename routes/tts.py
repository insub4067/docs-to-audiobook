"""음성 목록·미리듣기, TTS 합성 엔진, 작업 상태/오디오, 관리자 대용량
백그라운드 합성까지 — 서로 강하게 얽혀 있어(synthesize_text가 백그라운드
경로를 직접 호출하고, 백그라운드 작업이 다시 이 파일의 합성 엔진을 쓴다)
분리하면 순환 참조만 생기므로 한 모듈에 둔다.
"""
import os
import asyncio
import time
import uuid
import json
import secrets
import shutil
from datetime import datetime, timezone
import edge_tts
from fastapi import APIRouter, Request, BackgroundTasks, Form, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask

from state import (
    BASE_DIR, JOB_AUDIO_DIR, jobs, text_storage, MAX_SYNTH_CHARS,
    DOCUMENT_PART_CONCURRENCY, background_synthesis_lock, _has_enough_disk_for_synthesis,
    _supabase_or_503, _object_paths, AUDIOBOOK_BUCKET, resolve_job_owner, require_job_owner,
    enforce_rate_limit,
)
from text_processing import (
    build_document_representations, extract_markdown_headings,
    annotate_sentences_with_headings, annotate_sentences_with_tables, clean_tts_text,
)

router = APIRouter()

# 실제로 제공할 음성. edge-tts가 주는 ko-KR 음성은 3개뿐이고, 예전
# 메타데이터에 있던 지민/서현/순복/유진/현민은 존재하지 않아 선택할 수
# 없었다. 낭독에 쓸 두 개만 남긴다. 목록의 첫 번째가 기본값이다.
SUPPORTED_VOICES = [
    "ko-KR-HyunsuMultilingualNeural",
    "ko-KR-SunHiNeural",
]

# 음성 미리듣기. 짧은 한 문장이라 합성이 몇 초면 끝나고, 한 번 만들면
# 디스크에 캐시해 재사용한다.
VOICE_PREVIEW_TEXT = "안녕하세요. 이 목소리로 문서를 읽어 드릴게요. 오늘도 좋은 하루 보내세요."
VOICE_PREVIEW_DIR = os.path.join(BASE_DIR, "voice_previews")
os.makedirs(VOICE_PREVIEW_DIR, exist_ok=True)
voice_preview_lock = asyncio.Lock()

VOICE_METADATA = {
    "ko-KR-HyunsuMultilingualNeural": {
        "friendly_name": "현수 (자연스러운 낭독 - 남성)",
        "description": "멀티링구얼 신형 모델로 억양이 자연스럽고, 한글과 영어가 섞인 문장도 매끄럽게 읽습니다.",
        "tone": "natural", "use_case": ["novel", "audiobook", "documentation", "long_text"]
    },
    "ko-KR-SunHiNeural": {
        "friendly_name": "선희 (차분한 낭독 - 여성)",
        "description": "단정하고 차분한 여성 음성으로, 정보 전달이나 긴 호흡의 낭독에 적합합니다.",
        "tone": "formal", "use_case": ["news", "education", "audiobook", "long_text"]
    },
}


@router.get("/api/voices")
async def get_voices(tone: str = None, use_case: str = None):
    """음성 목록 반환. tone/use_case로 필터링 가능."""
    try:
        # Get all voices
        all_voices = await edge_tts.VoicesManager.create()
        voices = all_voices.voices

        filtered_voices = []
        for voice in voices:
            lang = voice.get("Locale", "")
            short_name = voice.get("ShortName", "")
            if short_name in SUPPORTED_VOICES:

                # Check if we have custom metadata for this Korean voice
                meta = VOICE_METADATA.get(short_name, {})
                friendly_name = meta.get("friendly_name", voice.get("FriendlyName", short_name))
                description = meta.get("description", "표준 신경망(Neural) 음성입니다.")

                voice_tone = meta.get("tone", "")
                voice_use_cases = meta.get("use_case", [])

                # Apply filters
                if tone and voice_tone != tone:
                    continue
                if use_case and use_case not in voice_use_cases:
                    continue

                filtered_voices.append({
                    "name": voice.get("Name", ""),
                    "short_name": short_name,
                    "gender": voice.get("Gender", ""),
                    "locale": lang,
                    "friendly_name": friendly_name,
                    "description": description,
                    "tone": voice_tone,
                    "use_case": voice_use_cases
                })

        # SUPPORTED_VOICES에 적은 순서를 유지한다. 첫 번째가 기본값이다.
        filtered_voices.sort(key=lambda x: SUPPORTED_VOICES.index(x["short_name"]))
        return filtered_voices
    except Exception as e:
        # edge-tts 목록 조회가 실패해도 UI가 비지 않도록. SUPPORTED_VOICES와
        # 같은 순서를 유지한다(첫 번째가 기본값).
        print(f"Voice list fetch failed, using fallback: {e}")
        return [
            {
                "name": short_name,
                "short_name": short_name,
                "gender": "Male" if "Hyunsu" in short_name else "Female",
                "locale": "ko-KR",
                "friendly_name": VOICE_METADATA[short_name]["friendly_name"],
                "description": VOICE_METADATA[short_name]["description"],
                "tone": VOICE_METADATA[short_name]["tone"],
                "use_case": VOICE_METADATA[short_name]["use_case"],
            }
            for short_name in SUPPORTED_VOICES
        ]


@router.get("/api/voices/{short_name}/preview")
async def get_voice_preview(short_name: str):
    """음성 미리듣기. 처음 요청될 때 한 번 만들고 디스크에 캐시한다."""
    # 경로에 그대로 들어가므로 반드시 허용 목록으로 검증한다
    if short_name not in SUPPORTED_VOICES:
        raise HTTPException(status_code=404, detail="지원하지 않는 음성입니다.")

    path = os.path.join(VOICE_PREVIEW_DIR, f"{short_name}.mp3")
    if not os.path.exists(path):
        async with voice_preview_lock:
            # 락을 기다리는 동안 다른 요청이 이미 만들었을 수 있다
            if not os.path.exists(path):
                try:
                    audio_bytes, _, _ = await synthesize_document(
                        VOICE_PREVIEW_TEXT, short_name, "+5%", "+0Hz"
                    )
                    if not audio_bytes:
                        raise RuntimeError("빈 오디오")
                    with open(path, "wb") as f:
                        f.write(audio_bytes)
                except Exception as e:
                    print(f"Voice preview generation failed ({short_name}): {e}")
                    raise HTTPException(status_code=503, detail="미리듣기를 만들지 못했습니다.")

    return FileResponse(path, media_type="audio/mpeg")


# Edge-TTS 동시 연결 상한. 이전에는 문서의 모든 청크를 상한 없이
# asyncio.gather로 한꺼번에 띄웠고(2만 자 = 25개 동시), 여러 작업이 겹치면
# 수백 개까지 늘어났다. 아래 재시도 로직이 필요했던 간헐적 연결 끊김이
# 사실상 이 과도한 동시성 때문이다. 작업 수와 무관하게 전역으로 묶는다.
TTS_CONCURRENCY = asyncio.Semaphore(8)

async def synthesize_chunk(chunk_index: int, text_chunk: str, voice: str, rate: str, pitch: str, max_attempts: int = 3):
    # TTS 발음용 깨끗한 텍스트
    tts_text = clean_tts_text(text_chunk)
    if not tts_text:
        tts_text = text_chunk

    # Edge-TTS는 특정 호스팅 환경에서 개별 연결이 간헐적으로 끊긴다.
    # 청크 단위로 재시도해, 문서 전체를 병렬 변환할 때 청크 하나의 일시적
    # 실패가 전체 asyncio.gather를 실패시키지 않도록 한다.
    last_error = None
    for attempt in range(max_attempts):
        try:
            # 백오프 sleep은 슬롯을 잡은 채로 기다리지 않도록 밖에 둔다
            async with TTS_CONCURRENCY:
                communicate = edge_tts.Communicate(tts_text, voice=voice, rate=rate, pitch=pitch)
                # bytes는 불변이라 += 누적은 조각마다 전체 복사본을 새로 만든다.
                # 조각을 모아 마지막에 한 번만 합친다.
                audio_parts = []
                sentences = []
                async for msg in communicate.stream():
                    if msg.get("type") == "audio":
                        audio_parts.append(msg.get("data"))
                    elif msg.get("type") == "SentenceBoundary":
                        offset_ms = msg.get("offset", 0) // 10000
                        duration_ms = msg.get("duration", 0) // 10000
                        sentences.append({
                            "text": msg.get("text", ""),
                            "start": offset_ms,
                            "end": offset_ms + duration_ms
                        })
                audio_data = b"".join(audio_parts)
                audio_parts.clear()
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

async def synthesize_document(raw_text: str, voice: str, rate: str, pitch: str, progress_callback=None) -> tuple:
    """Synthesize a full document into (audio_bytes, annotated_sentences, heading_index)."""
    display_markdown, text, tables = build_document_representations(raw_text)
    headings = extract_markdown_headings(display_markdown)

    chunks = split_tts_chunks(text)

    completed_chunks = 0

    async def synthesize_with_progress(chunk_index: int, chunk: str):
        nonlocal completed_chunks
        result = await synthesize_chunk(chunk_index, chunk, voice, rate, pitch)
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


async def synthesize_document_to_file(
    raw_text: str,
    voice: str,
    rate: str,
    pitch: str,
    output_path: str,
    progress_callback=None,
) -> tuple[list, list, str]:
    """긴 문서를 최대 다섯 묶음으로 병렬 합성해 MP3를 디스크에 기록한다."""
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
    part_paths = [f"{output_path}.part-{index}" for index in range(len(parts))]
    completed_chunks = 0

    async def synthesize_part(part_index: int, part: list[tuple[int, str]]):
        nonlocal completed_chunks
        part_sentences = []
        current_offset = 0
        with open(part_paths[part_index], "wb") as audio_file:
            for chunk_index, chunk in part:
                _, audio_data, sentences = await synthesize_chunk(chunk_index, chunk, voice, rate, pitch)
                audio_file.write(audio_data)
                for sentence in sentences:
                    part_sentences.append({
                        "text": sentence["text"],
                        "start": sentence["start"] + current_offset,
                        "end": sentence["end"] + current_offset,
                    })
                if sentences:
                    current_offset += max(sentence["end"] for sentence in sentences)
                completed_chunks += 1
                if progress_callback:
                    progress_callback(completed_chunks, len(chunks))
        return part_index, part_sentences, current_offset

    try:
        results = await asyncio.gather(*[
            synthesize_part(part_index, part)
            for part_index, part in enumerate(parts)
        ])
        results.sort(key=lambda result: result[0])

        combined_sentences = []
        current_offset = 0
        with open(output_path, "wb") as output_file:
            for part_index, part_sentences, part_duration in results:
                with open(part_paths[part_index], "rb") as part_file:
                    shutil.copyfileobj(part_file, output_file)
                os.remove(part_paths[part_index])
                for sentence in part_sentences:
                    combined_sentences.append({
                        "text": sentence["text"],
                        "start": sentence["start"] + current_offset,
                        "end": sentence["end"] + current_offset,
                    })
                current_offset += part_duration
    except Exception:
        try:
            os.remove(output_path)
        except OSError:
            pass
        raise
    finally:
        for part_path in part_paths:
            try:
                os.remove(part_path)
            except OSError:
                pass

    annotated_sentences, heading_index = annotate_sentences_with_headings(combined_sentences, headings)
    annotate_sentences_with_tables(annotated_sentences, tables)
    return annotated_sentences, heading_index, display_markdown


async def process_synthesis_task(job_id: str, raw_text: str, voice: str, rate: str, pitch: str):
    try:
        def update_progress(completed_chunks: int, total_chunks: int):
            jobs[job_id]["completed_chunks"] = completed_chunks
            jobs[job_id]["total_chunks"] = total_chunks

        audio_path = os.path.join(JOB_AUDIO_DIR, f"{job_id}.mp3")
        annotated_sentences, heading_index, display_markdown = await synthesize_document_to_file(
            raw_text, voice, rate, pitch, audio_path, progress_callback=update_progress
        )

        if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = "음성 합성 결과가 비어 있습니다."
            return

        jobs[job_id]["audio_path"] = audio_path
        jobs[job_id]["sentences"] = annotated_sentences
        jobs[job_id]["headings"] = heading_index
        jobs[job_id]["display_markdown"] = display_markdown
        jobs[job_id]["status"] = "completed"

    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)


def _store_background_audiobook(user_id: str, title: str, job: dict) -> str:
    """브라우저가 없어도 서버가 완성본을 사용자 보관함에 저장한다.

    Storage 업로드를 모두 마친 뒤에야 DB 행을 만든다 — 순서를 반대로 하면
    업로드가 중간에 실패했을 때 파일 없는 audiobooks 행이 고아로 남는다.
    """
    supabase = _supabase_or_503()
    audiobook_id = str(uuid.uuid4())
    audio_path, sentences_path = _object_paths(user_id, audiobook_id)
    storage = supabase.storage.from_(AUDIOBOOK_BUCKET)

    with open(job["audio_path"], "rb") as audio_file:
        storage.upload(audio_path, audio_file, {"content-type": "audio/mpeg"})
    try:
        storage.upload(
            sentences_path,
            json.dumps(job["sentences"], ensure_ascii=False).encode("utf-8"),
            {"content-type": "application/json"},
        )
    except Exception:
        # 문장 데이터 업로드가 실패하면 방금 올린 mp3도 고아가 되므로 함께 지운다.
        storage.remove([audio_path])
        raise

    supabase.table("audiobooks").insert({
        "id": audiobook_id,
        "user_id": user_id,
        "title": title[:255],
        "file_name": title[:255],
        "storage_path": audio_path,
    }).execute()
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
        "error": None,
        "created_at": time.time(),
        "user_id": user_id,
    }


async def process_background_synthesis_task(job_id: str, user_id: str, title: str, raw_text: str, voice: str, rate: str, pitch: str):
    """청크 단위 재시도로도 못 살린 실패는 문서 전체를 처음부터 다시 돌린다.

    몇 시간짜리 관리자 작업이 청크 하나의 일시적 오류 때문에 통째로
    날아가는 게 부분 재시도 인프라를 만드는 것보다 더 나쁘다고 판단해,
    "전체 성공 아니면 처음부터 다시"(all or nothing)로 간다 — 이미
    background_tasks로 돌아가는 fire-and-forget 작업이라 몇 번 더
    돌리는 비용은 낮고, 원문은 완료 전까지 DB에 그대로 있어 재시도가
    항상 안전하다.
    """
    supabase = _supabase_or_503()
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
                audiobook_id = await asyncio.to_thread(_store_background_audiobook, user_id, title, job)
                await asyncio.to_thread(
                    lambda: supabase.table("background_synthesis_jobs").update({
                        "status": "completed",
                        "source_text": None,
                        "audiobook_id": audiobook_id,
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                    }).eq("id", job_id).execute()
                )
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
    voice: str = Form("ko-KR-HyunsuMultilingualNeural"),
    rate: str = Form("+5%"),
    pitch: str = Form("+0Hz"),
    authorization: str = Header(None),
    anonymous_session: str = Header(None, alias="X-Anonymous-Session")
):
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

        supabase = _supabase_or_503()
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

            if not _has_enough_disk_for_synthesis(len(raw_text)):
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
        )
        return {"job_id": job_id, "background_started": True}

    job_id = _new_job_id_and_state()
    background_tasks.add_task(process_synthesis_task, job_id, raw_text, voice, rate, pitch)
    return {"job_id": job_id}

@router.get("/api/job/{job_id}")
async def get_job_status(
    job_id: str,
    authorization: str = Header(None),
    anonymous_session: str = Header(None, alias="X-Anonymous-Session")
):
    job = require_job_owner(job_id, authorization, anonymous_session)

    if job["status"] == "completed":
        # 오디오는 별도 엔드포인트에서 파일로 스트리밍한다. 여기서는
        # 메타데이터만 주고 job은 남겨둔다(오디오를 받아가야 정리된다).
        return JSONResponse(content={
            "status": "completed",
            "audio_url": f"/api/job/{job_id}/audio",
            "sentences": job["sentences"],
            "headings": job.get("headings", []),
            "display_markdown": job.get("display_markdown", ""),
        })

    return JSONResponse(content={
        "status": job["status"],
        "error": job.get("error"),
        "completed_chunks": job.get("completed_chunks", 0),
        "total_chunks": job.get("total_chunks", 0),
    })


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
        supabase = _supabase_or_503()
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
            asyncio.create_task(process_background_synthesis_task(
                job_id, row["user_id"], row["title"], row["source_text"],
                row["voice"], row["rate"], row["pitch"],
            ))
    except Exception as e:
        print(f"Background job resume failed: {e}")


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
