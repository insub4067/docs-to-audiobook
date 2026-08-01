import os
from dotenv import load_dotenv
load_dotenv()

import uuid
import docx
import pypdf
import asyncio
import html
import time
import re
import json
import shutil
import secrets
from collections import Counter
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Response, BackgroundTasks, Header, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.background import BackgroundTask
import edge_tts
import ipaddress
import socket
import requests
from urllib.parse import urlparse, urljoin
import mimetypes
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("application/javascript", ".js")

from state import (
    BASE_DIR, UPLOAD_DIR, STATIC_DIR, SHARED_DIR, JOB_AUDIO_DIR,
    MAX_UPLOAD_BYTES, MAX_ADMIN_UPLOAD_BYTES, MAX_SYNTH_CHARS, MAX_ADMIN_SYNTH_CHARS,
    AUDIO_BYTES_PER_CHAR_ESTIMATE, DISK_ESTIMATE_SAFETY_FACTOR, DISK_RESERVE_BYTES,
    DOCUMENT_PART_CONCURRENCY, large_admin_upload_lock, background_synthesis_lock,
    _too_large, read_upload_limited, save_upload_limited, _rate_buckets, enforce_rate_limit,
    AUDIOBOOK_BUCKET, SIGNED_URL_TTL, require_user_id, resolve_job_owner, require_job_owner,
    _supabase_or_503, require_admin_user, _admin_emails, upload_limit_for, synth_limit_for,
    _has_enough_disk_for_synthesis, _object_paths, APP_BUILD_ID, text_storage, jobs,
)
from text_processing import (
    extract_hwp_text, _looks_like_garbled_pdf_extraction, extract_text, parse_heading_line,
    _pdf_layout_cells, normalize_pdf_for_reading, _markdown_table_cells, _is_markdown_table_separator,
    normalize_markdown_for_reading, extract_markdown_tables, build_document_representations,
    _normalized_match_text, annotate_sentences_with_tables, preprocess_text,
    extract_markdown_headings, annotate_sentences_with_headings, clean_tts_text,
)

app = FastAPI(title="Docs to Audiobook Converter - Hybrid")

# 프론트엔드는 같은 출처에서 상대 경로로만 API를 호출하므로 와일드카드가
# 필요 없다. allow_origins=["*"] 와 allow_credentials=True 조합은 잘못된
# 설정이기도 하다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://docs-to-audiobook.onrender.com",
        "https://docs-to-audiobook.fly.dev",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

from routes import extract_url as extract_url_routes
from routes import upload as upload_routes
app.include_router(extract_url_routes.router)
app.include_router(upload_routes.router)

# Directories config

# ---- 리소스 상한 ----
# 업로드는 지금까지 클라이언트에서만 검사했다. API를 직접 호출하면 그대로
# 통과해 파일 전체가 메모리에 올라간다.
# 압축 전 원본 PDF가 175MB대까지 나올 수 있다는 실사용 사례가 있어
# 여유를 두고 250MB로 잡는다. 파싱 자체의 메모리 사용량은 파일
# 크기만으로 정확히 예측할 수 없다(PDF 내부 객체 구조에 따라 다름) —
# 실제로 문제가 되면(느려지거나 인스턴스가 재시작되면) 다시 낮춘다.

# 합성 문자 수 상한. 오디오는 문자당 약 903바이트이고 합성 피크는 그 2배쯤
# 되므로, 10MB 텍스트(약 350만 자)를 그대로 받으면 오디오만 2.9GB가 되어
# 반드시 죽는다. 10만 자면 약 4시간 분량이라 실사용에는 충분하다.

# 관리자 경로(synthesize_document_to_file)는 위와 달리 메모리에 오디오를
# 쌓지 않고 곧장 디스크에 쓰므로 위 903바이트/자 계산이 적용되지 않는다 —
# 실제 제약은 디스크다. 고정 숫자로 "안전할 것 같은 상한"을 추측하는
# 대신, 요청이 올 때마다 실제 여유 디스크를 재보고 판단한다
# (_has_enough_disk_for_synthesis). 아래 값은 그 실제 판단 전에 걸러낼
# 순수 방어용 상한이다 — 손상된 PDF 추출 등으로 텍스트가 병적으로
# 부풀었을 때를 막을 뿐, 정상적인 문서에서는 사실상 걸릴 일이 없다.

# 문자당 오디오 바이트 추정치(위 MAX_SYNTH_CHARS 계산과 동일 근거).
# 결합 단계에서 최종 파일과 파트 파일이 잠깐 동시에 존재해 순간 디스크
# 사용량이 최종 크기의 최대 2배까지 갈 수 있어 SAFETY_FACTOR로 반영한다.

# 긴 관리자 문서는 다섯 묶음으로 나눠 각각의 MP3를 디스크에 기록한다.
# 묶음 안의 청크는 순서대로 처리해 메모리에 오디오를 쌓지 않는다.

# 1GB 인스턴스에서는 대용량 문서의 텍스트 추출을 병렬로 처리하면 메모리
# 여유가 빠르게 사라진다. 관리자 대용량 업로드는 한 번에 하나만 처리한다.

# 위 락은 업로드(텍스트 추출) 단계만 막는다. 실제로 CPU를 오래 쓰는 건
# TTS 합성이므로, 백그라운드 합성 작업 자체도 동시에 하나만 실행되게
# 별도로 막는다. 단일 인스턴스 전제라 프로세스 내 락으로 충분하다.

# 공유되는 오디오는 오디오북 전체라 크다. MAX_SYNTH_CHARS(10만 자) 분량이
# 약 90MB이므로 여유를 둔다. 대신 메모리에 담지 않고 디스크로 흘려보낸다.
MAX_SHARE_AUDIO_BYTES = 120 * 1024 * 1024
MAX_SHARE_METADATA_BYTES = 2 * 1024 * 1024




def validate_share_id(share_id: str) -> str:
    if share_id == "default_book" or re.fullmatch(r"(?:[0-9a-f]{12}|[0-9a-f]{8}-[0-9a-f]{3})", share_id):
        return share_id
    raise HTTPException(status_code=404, detail="공유 링크가 만료되었거나 존재하지 않습니다.")


def parse_share_metadata(sentences: str, headings: str) -> tuple[list, list]:
    if len(sentences.encode("utf-8")) + len(headings.encode("utf-8")) > MAX_SHARE_METADATA_BYTES:
        raise _too_large(MAX_SHARE_METADATA_BYTES)
    try:
        parsed_sentences = json.loads(sentences)
        parsed_headings = json.loads(headings)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="문장 정보는 올바른 JSON 배열이어야 합니다.")
    if not isinstance(parsed_sentences, list) or not isinstance(parsed_headings, list):
        raise HTTPException(status_code=400, detail="문장 정보는 올바른 JSON 배열이어야 합니다.")
    return parsed_sentences, parsed_headings




# ---- 레이트 리밋 ----
# 모든 콘텐츠 엔드포인트가 무인증이라 합성 요청을 무제한으로 받을 수 있다.
# 단일 인스턴스라 인메모리 슬라이딩 윈도우로 충분하다.



# ---- 클라우드 보관함 ----




















def _parse_event_time(value: str | None):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except (TypeError, ValueError):
        return None


def load_admin_metrics():
    """관리자에게만 사용자·이벤트 집계와 지표별 사용자 목록을 반환한다."""
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)
    thirty_days_ago = now - timedelta(days=30)
    supabase = _supabase_or_503()
    try:
        users = supabase.table("users").select("id,full_name,email,created_at").execute().data or []
        audiobooks = supabase.table("audiobooks").select("id,user_id,created_at").execute().data or []
        events = supabase.table("product_events").select("user_id,event_name,created_at") \
            .gte("created_at", thirty_days_ago.isoformat()).execute().data or []
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"관리자 통계를 불러오지 못했습니다: {e}")

    dated_events = [(event, _parse_event_time(event.get("created_at"))) for event in events]
    recent_events = [(event, event_time) for event, event_time in dated_events if event_time]
    weekly_active_users = {event["user_id"] for event, event_time in recent_events if event_time >= week_ago}
    daily_active_users = {event["user_id"] for event, event_time in recent_events if event_time >= now - timedelta(days=1)}
    started = sum(event["event_name"] == "generation_started" for event, _ in recent_events)
    completed = sum(event["event_name"] == "generation_completed" for event, _ in recent_events)
    failed = sum(event["event_name"] == "generation_failed" for event, _ in recent_events)

    first_event_by_user = {}
    for event, event_time in recent_events:
        user_id = event.get("user_id")
        if user_id and (user_id not in first_event_by_user or event_time < first_event_by_user[user_id]):
            first_event_by_user[user_id] = event_time
    week_one_cohort = {
        user_id for user_id, event_time in first_event_by_user.items()
        if two_weeks_ago <= event_time < week_ago
    }
    returning_users = {
        event["user_id"] for event, event_time in recent_events
        if event_time >= week_ago and event.get("user_id") in week_one_cohort
    }

    users_by_id = {user["id"]: user for user in users}

    def user_list(user_ids, meta_by_id=None):
        people = []
        for user_id in user_ids:
            user = users_by_id.get(user_id)
            if not user:
                continue
            people.append({
                "name": user.get("full_name") or "이름 없음",
                "email": user.get("email") or "",
                "meta": (meta_by_id or {}).get(user_id, ""),
            })
        return sorted(people, key=lambda person: (person["name"], person["email"]))

    generation_counts = {}
    playback_counts = {}
    for event, _ in recent_events:
        user_id = event.get("user_id")
        if not user_id:
            continue
        if event["event_name"] in {"generation_completed", "generation_failed"}:
            counts = generation_counts.setdefault(user_id, {"completed": 0, "failed": 0})
            counts["completed" if event["event_name"] == "generation_completed" else "failed"] += 1
        if event["event_name"] == "playback_started":
            playback_counts[user_id] = playback_counts.get(user_id, 0) + 1

    audiobook_counts = {}
    for audiobook in audiobooks:
        user_id = audiobook.get("user_id")
        if user_id:
            audiobook_counts[user_id] = audiobook_counts.get(user_id, 0) + 1

    metric_details = {
        "total_users": user_list(
            users_by_id,
            {user["id"]: f"가입일 {str(user.get('created_at') or '')[:10]}" for user in users},
        ),
        "daily_active_users": user_list(daily_active_users, {user_id: "최근 24시간 활동" for user_id in daily_active_users}),
        "weekly_active_users": user_list(weekly_active_users, {user_id: "최근 7일 활동" for user_id in weekly_active_users}),
        "week_one_retention_rate": user_list(
            week_one_cohort,
            {user_id: "재방문" if user_id in returning_users else "미재방문" for user_id in week_one_cohort},
        ),
        "generation_success_rate": user_list(
            generation_counts,
            {
                user_id: f"완료 {counts['completed']}회 · 실패 {counts['failed']}회"
                for user_id, counts in generation_counts.items()
            },
        ),
        "playback_started_30d": user_list(
            playback_counts,
            {user_id: f"재생 시작 {count}회" for user_id, count in playback_counts.items()},
        ),
        "total_audiobooks": user_list(
            audiobook_counts,
            {user_id: f"오디오북 {count}권" for user_id, count in audiobook_counts.items()},
        ),
    }

    return {
        "total_users": len(users),
        "new_users_7d": sum((_parse_event_time(user.get("created_at")) or now) >= week_ago for user in users),
        "total_audiobooks": len(audiobooks),
        "daily_active_users": len(daily_active_users),
        "weekly_active_users": len(weekly_active_users),
        "generation_started_30d": started,
        "generation_completed_30d": completed,
        "generation_failed_30d": failed,
        "generation_success_rate": round(completed / (completed + failed) * 100) if completed + failed else None,
        "playback_started_30d": sum(event["event_name"] == "playback_started" for event, _ in recent_events),
        "week_one_retention_rate": round(len(returning_users) / len(week_one_cohort) * 100) if week_one_cohort else None,
        "retention_cohort_size": len(week_one_cohort),
        "metric_details": metric_details,
    }




# App build ID: generated once at server startup.
# Changes on every redeploy (new process start), used by client to detect updates.

# In-memory storage for extracted texts
# Keeps text temporarily for 30 minutes. Auto-expired by background task.

# In-memory storage for synthesis jobs
# Tracks the status of background edge-tts generation tasks

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


































@app.get("/api/voices")
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


@app.get("/api/voices/{short_name}/preview")
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


@app.post("/api/synthesize")
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

@app.get("/api/job/{job_id}")
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


@app.get("/api/job/{job_id}/audio")
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

# Serve static files (HTML, CSS, JS)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Serve PWA Configs at root level for scope compliance
@app.get("/api/version")
async def get_version():
    """Returns the server's build ID. Client polls this on foreground resume to detect redeployment."""
    return JSONResponse(content={"build_id": APP_BUILD_ID})


@app.get("/api/config")
async def get_config():
    """클라이언트 설정. 소셜 로그인 클라이언트 ID는 브라우저에 노출되는 공개
    값이라 코드에 박지 않고 환경변수에서 내려준다(그동안 플레이스홀더가 박혀
    있어 로그인이 아예 동작하지 않았다).

    제공자를 늘릴 때는 아래 dict에 한 줄만 추가하면 된다. 값이 비어 있는
    제공자는 클라이언트가 알아서 건너뛴다."""
    providers = {
        "google": os.getenv("GOOGLE_CLIENT_ID", ""),
        # "kakao": os.getenv("KAKAO_JS_KEY", ""),
        # "naver": os.getenv("NAVER_CLIENT_ID", ""),
        # "apple": os.getenv("APPLE_CLIENT_ID", ""),
    }
    return JSONResponse(content={
        "providers": {k: v for k, v in providers.items() if v},
        # 이전 클라이언트 호환용
        "google_client_id": providers.get("google", "")
    })


@app.post("/api/events")
async def create_product_event(request: Request, payload: dict, authorization: str = Header(None)):
    """개인 콘텐츠 없이 제품 이용 지표에 필요한 이벤트만 기록한다."""
    user_id = require_user_id(authorization)
    enforce_rate_limit(request, "product_event", limit=120, window_sec=600)
    event_name = payload.get("event_name")
    if event_name not in {"generation_started", "generation_completed", "generation_failed", "playback_started"}:
        raise HTTPException(status_code=400, detail="지원하지 않는 이벤트입니다.")
    try:
        _supabase_or_503().table("product_events").insert({
            "user_id": user_id,
            "event_name": event_name,
        }).execute()
        return {"recorded": event_name}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"이벤트를 기록하지 못했습니다: {e}")


@app.get("/api/admin/metrics")
async def get_admin_metrics(authorization: str = Header(None)):
    require_admin_user(authorization)
    return load_admin_metrics()

@app.get("/manifest.json")
async def get_manifest():
    return FileResponse(os.path.join(STATIC_DIR, "manifest.json"), media_type="application/json")

@app.get("/sw.js")
async def get_serviceworker():
    return FileResponse(os.path.join(STATIC_DIR, "sw.js"), media_type="application/javascript")

@app.get("/")
async def read_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse(status_code=404, content={"message": "Frontend static file index.html not found. Build the frontend first."})


@app.get("/admin")
async def read_admin_dashboard():
    admin_path = os.path.join(STATIC_DIR, "admin.html")
    if os.path.exists(admin_path):
        return FileResponse(admin_path)
    return JSONResponse(status_code=404, content={"message": "관리자 대시보드를 찾을 수 없습니다."})


@app.get("/admin/metrics/{metric_name}")
async def read_admin_metric_page(metric_name: str):
    metric_path = os.path.join(STATIC_DIR, "admin-metric.html")
    if os.path.exists(metric_path):
        return FileResponse(metric_path)
    return JSONResponse(status_code=404, content={"message": "관리자 지표 화면을 찾을 수 없습니다."})

# --------------------------------------------------
# Share Feature: 24-hour temporary server storage
# --------------------------------------------------

@app.post("/api/share")
async def create_share(
    request: Request,
    audio: UploadFile = File(...),
    title: str = Form(...),
    sentences: str = Form(...),
    headings: str = Form("[]"),
    authorization: str = Header(None)
):
    """클라이언트가 오디오북을 공유할 때 서버에 임시 저장 (24시간 후 자동 삭제)"""
    # 오디오북 생성이 로그인 전용이므로 공유도 같이 맞춘다. 무인증으로 두면
    # 남의 도메인에 임의 콘텐츠(최대 120MB)를 올리는 통로가 된다.
    # 공유 링크 열람(GET)은 받는 사람을 위해 계속 공개로 둔다.
    require_user_id(authorization)
    enforce_rate_limit(request, "share", limit=20, window_sec=3600)

    parsed_sentences, parsed_headings = parse_share_metadata(sentences, headings)

    share_id = uuid.uuid4().hex[:12]
    share_dir = os.path.join(SHARED_DIR, share_id)
    os.makedirs(share_dir, exist_ok=True)

    # Save audio file
    audio_path = os.path.join(share_dir, "audio.mp3")
    await save_upload_limited(audio, audio_path, MAX_SHARE_AUDIO_BYTES)

    # Save metadata
    meta = {
        "title": title,
        "sentences": parsed_sentences,
        "headings": parsed_headings,
        "created_at": time.time(),
    }
    meta_path = os.path.join(share_dir, "meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)

    return {"share_id": share_id}

@app.get("/api/share/{share_id}")
async def get_share_meta(share_id: str):
    """공유된 오디오북의 메타데이터 (제목 + 문장 타이밍) 반환"""
    share_id = validate_share_id(share_id)
    if share_id == "default_book":
        _, meta_path = default_book_paths()
        if not os.path.exists(meta_path):
            raise HTTPException(status_code=404, detail="기본 제공 오디오북을 아직 준비 중입니다.")
    else:
        meta_path = os.path.join(SHARED_DIR, share_id, "meta.json")
        if not os.path.exists(meta_path):
            raise HTTPException(status_code=404, detail="공유 링크가 만료되었거나 존재하지 않습니다.")
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    return {
        "title": meta["title"],
        "sentences": meta["sentences"],
        "headings": meta.get("headings", []),
        "audio_url": f"/api/share/{share_id}/audio"
    }

@app.get("/api/share/{share_id}/audio")
async def get_share_audio(share_id: str):
    """공유된 오디오 MP3 스트리밍"""
    share_id = validate_share_id(share_id)
    if share_id == "default_book":
        audio_path, _ = default_book_paths()
        if not os.path.exists(audio_path):
            raise HTTPException(status_code=404, detail="기본 제공 오디오북을 아직 준비 중입니다.")
    else:
        audio_path = os.path.join(SHARED_DIR, share_id, "audio.mp3")
        if not os.path.exists(audio_path):
            raise HTTPException(status_code=404, detail="공유 오디오가 만료되었거나 존재하지 않습니다.")
    return FileResponse(audio_path, media_type="audio/mpeg", filename="audiobook.mp3")

@app.get("/share/{share_id}")
async def serve_shared_page(share_id: str):
    """공유 링크로 접속 시 동일한 index.html 서빙 (JS가 URL을 파싱하여 Reader 모드 자동 진입)"""
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail="Page not found")

# --------------------------------------------------
# Default Book: 서버 기동 시 기본 제공 오디오북을 미리 생성해 캐시
# --------------------------------------------------

DEFAULT_BOOK_DIR = os.path.join(BASE_DIR, "default_book")
DEFAULT_BOOK_SOURCE = os.path.join(STATIC_DIR, "samples", "demian.txt")
DEFAULT_BOOK_TITLE = "데미안"
DEFAULT_BOOK_VOICE = SUPPORTED_VOICES[0]

default_book_state = {"status": "pending", "error": None}
default_book_lock = asyncio.Lock()


def _default_book_fingerprint() -> str:
    """음성 + 원문 내용으로 캐시 키를 만든다.

    음성만 넣었을 때는 원문을 바꿔도 키가 그대로라, 예전 내용으로 만든
    오디오가 계속 재사용됐다(축약본 3챕터가 전문으로 바꾼 뒤에도 남았다).
    내용 해시를 함께 넣어 원문이 바뀌면 자동으로 다시 만들게 한다."""
    import hashlib

    h = hashlib.sha256()
    h.update(DEFAULT_BOOK_VOICE.encode())
    try:
        with open(DEFAULT_BOOK_SOURCE, "rb") as f:
            h.update(f.read())
    except OSError:
        pass
    return f"{DEFAULT_BOOK_VOICE}.{h.hexdigest()[:10]}"


def default_book_paths():
    fp = _default_book_fingerprint()
    return (
        os.path.join(DEFAULT_BOOK_DIR, f"audio.{fp}.mp3"),
        os.path.join(DEFAULT_BOOK_DIR, f"meta.{fp}.json"),
    )


# 기본 제공 오디오북을 클라우드에 한 번만 만들어 두는 자리.
# 디스크는 재배포마다 날아가므로 여기 없으면 부팅할 때마다 36,000자를
# 다시 합성하게 되고, 공유 CPU 1개를 점유해 사용자 변환까지 굶긴다.
# 로컬과 같은 키(음성 + 원문 해시)를 클라우드에도 쓴다


def default_book_remote_keys():
    fp = _default_book_fingerprint()
    return (
        f"_default/demian.{fp}.mp3",
        f"_default/demian.{fp}.meta.json",
    )


def _restore_default_book_from_cloud(audio_path: str, meta_path: str) -> bool:
    """클라우드에 있으면 내려받아 디스크에 놓는다. 성공하면 True."""
    try:
        from auth import get_supabase_client

        client = get_supabase_client(use_service_role=True)
        if not client:
            return False
        remote_audio, remote_meta = default_book_remote_keys()
        storage = client.storage.from_(AUDIOBOOK_BUCKET)
        audio = storage.download(remote_audio)
        meta = storage.download(remote_meta)
        if not audio or not meta:
            return False
        os.makedirs(DEFAULT_BOOK_DIR, exist_ok=True)
        with open(audio_path, "wb") as f:
            f.write(audio)
        with open(meta_path, "wb") as f:
            f.write(meta)
        print("Default audiobook restored from cloud.")
        return True
    except Exception as e:
        print(f"Default book not in cloud yet ({e}).")
        return False


def _upload_default_book_to_cloud(audio_path: str, meta_path: str) -> None:
    """다음 부팅부터 다시 만들지 않도록 클라우드에 올려둔다."""
    try:
        from auth import get_supabase_client

        client = get_supabase_client(use_service_role=True)
        if not client:
            return
        remote_audio, remote_meta = default_book_remote_keys()
        storage = client.storage.from_(AUDIOBOOK_BUCKET)
        with open(audio_path, "rb") as f:
            storage.upload(remote_audio, f.read(),
                           {"content-type": "audio/mpeg", "upsert": "true"})
        with open(meta_path, "rb") as f:
            storage.upload(remote_meta, f.read(),
                           {"content-type": "application/json", "upsert": "true"})
        print("Default audiobook uploaded to cloud.")
    except Exception as e:
        # 올리기 실패해도 이번 부팅에서는 이미 로컬에 있으니 서비스는 된다
        print(f"Default book cloud upload failed: {e}")


async def prepare_default_book_from_cache() -> bool:
    """합성 없이 준비만 시도한다(디스크 → 클라우드). 부팅 시 호출된다."""
    audio_path, meta_path = default_book_paths()

    if os.path.exists(audio_path) and os.path.exists(meta_path):
        default_book_state["status"] = "ready"
        print("Default audiobook already exists on disk.")
        return True

    if await asyncio.to_thread(_restore_default_book_from_cloud, audio_path, meta_path):
        default_book_state["status"] = "ready"
        return True

    # 아직 없다. 합성은 실제 요청이 올 때 한 번만 한다.
    default_book_state["status"] = "pending"
    return False


async def generate_default_book():
    """기본 제공 오디오북을 준비한다. 디스크 → 클라우드 → 생성 순으로 찾는다."""
    audio_path, meta_path = default_book_paths()

    if await prepare_default_book_from_cache():
        return

    if not os.path.exists(DEFAULT_BOOK_SOURCE):
        default_book_state["status"] = "error"
        default_book_state["error"] = "기본 제공 문서를 찾을 수 없습니다."
        print(f"Default book source missing: {DEFAULT_BOOK_SOURCE}")
        return

    default_book_state["status"] = "generating"
    print(f"Starting default audiobook generation from {DEFAULT_BOOK_SOURCE}...")
    try:
        os.makedirs(DEFAULT_BOOK_DIR, exist_ok=True)
        raw_text = extract_text(DEFAULT_BOOK_SOURCE, "demian.txt")
        # edge-tts 경로는 오디오 바이트를 돌려주므로 여기서 디스크에 쓴다
        audio_bytes, sentences, headings = await synthesize_document(
            raw_text, DEFAULT_BOOK_VOICE, "+5%", "+0Hz"
        )
        if not audio_bytes:
            raise RuntimeError("음성 합성 결과가 비어 있습니다.")
        with open(audio_path, "wb") as f:
            f.write(audio_bytes)
        del audio_bytes

        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump({
                "title": DEFAULT_BOOK_TITLE,
                "sentences": sentences,
                "headings": headings,
                "char_count": len(raw_text),
            }, f, ensure_ascii=False)

        default_book_state["status"] = "ready"
        default_book_state["error"] = None
        print(f"Default book generated.")
        # 다음 부팅부터는 재합성 없이 이걸 그대로 쓴다
        await asyncio.to_thread(_upload_default_book_to_cloud, audio_path, meta_path)
    except Exception as e:
        default_book_state["status"] = "error"
        default_book_state["error"] = str(e)
        print(f"Default book generation failed: {e}")


@app.get("/api/default-book")
async def get_default_book():
    """기본 제공 오디오북의 상태 및 메타데이터를 반환.
    Edge-TTS 접속이 간헐적으로 막히는 호스팅 환경 특성상, 이전 시도가
    실패한 상태라면 요청이 들어올 때마다 재시도한다 (동시 중복 실행은 락으로 방지)."""
    audio_path, meta_path = default_book_paths()

    # pending(부팅 시 캐시에 없었음) 또는 error(이전 시도 실패)면 여기서 한 번
    # 생성한다. 부팅 시가 아니라 실제 요청 시점에 하는 이유는, 기동 직후
    # 합성을 시작하면 공유 CPU를 점유해 사용자 변환이 막히기 때문이다.
    if default_book_state["status"] in ("pending", "error"):
        async def start_generation():
            async with default_book_lock:
                if default_book_state["status"] in ("pending", "error"):
                    await generate_default_book()
        asyncio.create_task(start_generation())
        return JSONResponse(content={
            "status": "generating",
            "error": None,
        })

    if default_book_state["status"] != "ready" or not os.path.exists(meta_path):
        return JSONResponse(content={
            "status": default_book_state["status"],
            "error": default_book_state["error"],
        })

    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    return JSONResponse(content={
        "status": "ready",
        "title": meta["title"],
        "sentences": meta["sentences"],
        "headings": meta.get("headings", []),
        "char_count": meta.get("char_count", 0),
        "audio_url": "/api/default-book/audio",
        "version": _default_book_fingerprint(),
    })


@app.get("/api/default-book/audio")
async def get_default_book_audio():
    audio_path, _ = default_book_paths()
    if not os.path.exists(audio_path):
        raise HTTPException(status_code=404, detail="기본 제공 오디오북이 아직 준비되지 않았습니다.")
    return FileResponse(audio_path, media_type="audio/mpeg", filename="sherlock-holmes.mp3")

@app.get("/api/audio/{job_id}.mp3")
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


async def cleanup_expired_files_loop():
    while True:
        try:
            now = time.time()
            # 1. Clean memory text storage (older than 30 minutes)
            expired_keys = []
            for key, data in text_storage.items():
                created_at = data.get("created_at", 0)
                if now - created_at > 1800:
                    expired_keys.append(key)
            for key in expired_keys:
                text_storage.pop(key, None)

            # 2. Clean shared audiobooks (older than 24 hours)
            if os.path.exists(SHARED_DIR):
                for share_id in os.listdir(SHARED_DIR):
                    share_dir = os.path.join(SHARED_DIR, share_id)
                    meta_path = os.path.join(share_dir, "meta.json")
                    if os.path.isdir(share_dir) and os.path.exists(meta_path):
                        try:
                            with open(meta_path, "r") as f:
                                meta = json.load(f)
                            if now - meta.get("created_at", 0) > 86400:  # 24 hours
                                shutil.rmtree(share_dir)
                                print(f"Cleaned expired share: {share_id}")
                        except Exception:
                            pass

            # 3. 클라이언트가 받아가지 않은 job 오디오 정리 (30분 경과)
            for jid in [k for k, v in jobs.items()
                        if now - v.get("created_at", now) > 1800]:
                job = jobs.pop(jid, None)
                if job and job.get("audio_path"):
                    try:
                        os.remove(job["audio_path"])
                    except OSError:
                        pass
                print(f"Cleaned expired job: {jid}")

            # 고아 파일(서버 재시작 등으로 jobs에 없는 파일)도 정리
            if os.path.exists(JOB_AUDIO_DIR):
                for fname in os.listdir(JOB_AUDIO_DIR):
                    fpath = os.path.join(JOB_AUDIO_DIR, fname)
                    try:
                        if os.path.isfile(fpath) and now - os.path.getmtime(fpath) > 1800:
                            os.remove(fpath)
                    except OSError:
                        pass
        except Exception as e:
            print(f"Error in cleanup background task: {e}")
        
        await asyncio.sleep(600)  # Every 10 minutes

# ====================================================
# 클라우드 보관함 (로컬 우선 + 클라우드 백업)
#
# IndexedDB가 재생 원본이고 여기는 백업 및 기기 간 전달 통로다.
# 오디오북은 만든 뒤 편집이 없어 생성/삭제만 있으므로 충돌 병합이 필요 없다.
# 파일 본체는 클라이언트가 서명 URL로 Supabase와 직접 주고받는다 —
# 서버를 거치면 최대 90MB가 매번 인스턴스 메모리를 지나간다.
# ====================================================

@app.post("/api/audiobooks")
async def create_audiobook(request: Request, payload: dict, authorization: str = Header(None)):
    """메타데이터 행을 만들고 업로드용 서명 URL을 돌려준다."""
    user_id = require_user_id(authorization)
    enforce_rate_limit(request, "audiobook_create", limit=60, window_sec=600)

    title = (payload.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="제목이 필요합니다.")

    supabase = _supabase_or_503()
    audiobook_id = str(uuid.uuid4())
    audio_path, sentences_path = _object_paths(user_id, audiobook_id)

    try:
        supabase.table("audiobooks").insert({
            "id": audiobook_id,
            "user_id": user_id,
            "title": title[:255],
            "file_name": (payload.get("file_name") or title)[:255],
            "duration_seconds": payload.get("duration_seconds"),
            "storage_path": audio_path,
        }).execute()

        storage = supabase.storage.from_(AUDIOBOOK_BUCKET)
        return {
            "id": audiobook_id,
            "audio_upload": storage.create_signed_upload_url(audio_path),
            "sentences_upload": storage.create_signed_upload_url(sentences_path),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"클라우드 등록에 실패했습니다: {e}")


@app.get("/api/audiobooks")
async def list_audiobooks(authorization: str = Header(None)):
    """내 오디오북 목록. 각 항목에 다운로드용 서명 URL을 붙인다."""
    user_id = require_user_id(authorization)
    supabase = _supabase_or_503()

    try:
        rows = supabase.table("audiobooks").select("*").eq("user_id", user_id) \
            .order("created_at", desc=True).execute().data or []
        storage = supabase.storage.from_(AUDIOBOOK_BUCKET)

        items = []
        for row in rows:
            audio_path, sentences_path = _object_paths(user_id, row["id"])
            item = dict(row)
            # 오디오가 없으면 재생이 불가능하므로 그 항목만 목록에서 제외한다
            # (업로드가 중간에 끊긴 행). 목록 전체를 실패시키지는 않는다.
            try:
                item["audio_url"] = storage.create_signed_url(audio_path, SIGNED_URL_TTL)["signedURL"]
            except Exception:
                continue
            # 문장 데이터는 없어도 오디오 재생은 되므로 선택 사항으로 둔다
            try:
                item["sentences_url"] = storage.create_signed_url(sentences_path, SIGNED_URL_TTL)["signedURL"]
            except Exception:
                item["sentences_url"] = None
            items.append(item)
        return {"audiobooks": items}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"목록을 불러오지 못했습니다: {e}")


@app.patch("/api/audiobooks/{audiobook_id}")
async def update_audiobook(audiobook_id: str, payload: dict, authorization: str = Header(None)):
    """내 오디오북 제목을 수정한다."""
    user_id = require_user_id(authorization)
    title = (payload.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="제목이 필요합니다.")

    supabase = _supabase_or_503()
    try:
        response = supabase.table("audiobooks").update({"title": title[:255]}) \
            .eq("id", audiobook_id).eq("user_id", user_id).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="해당 오디오북을 찾을 수 없습니다.")
        return {"id": audiobook_id, "title": title[:255]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"제목 수정에 실패했습니다: {e}")


def _validate_playback_state(payload: dict) -> tuple[float, float, str]:
    position = payload.get("current_time_seconds")
    speed = payload.get("playback_speed", 1.0)
    repeat_mode = payload.get("repeat_mode", "off")
    if not isinstance(position, (int, float)) or isinstance(position, bool) or position < 0:
        raise HTTPException(status_code=400, detail="재생 위치가 올바르지 않습니다.")
    if speed not in (0.75, 1.0, 1.25, 1.5, 2.0):
        raise HTTPException(status_code=400, detail="재생 속도가 올바르지 않습니다.")
    if repeat_mode not in ("off", "all", "one"):
        raise HTTPException(status_code=400, detail="반복 모드가 올바르지 않습니다.")
    return position, speed, repeat_mode


@app.get("/api/audiobooks/{audiobook_id}/playback")
async def get_playback_state(audiobook_id: str, authorization: str = Header(None)):
    """현재 계정의 오디오북 재생 상태를 반환한다."""
    user_id = require_user_id(authorization)
    supabase = _supabase_or_503()
    try:
        response = supabase.table("playback_history").select("*") \
            .eq("audiobook_id", audiobook_id).eq("user_id", user_id).maybe_single().execute()
        if response.data:
            return response.data
        return {
            "audiobook_id": audiobook_id,
            "current_time_seconds": 0,
            "playback_speed": 1.0,
            "repeat_mode": "off",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"재생 상태를 불러오지 못했습니다: {e}")


@app.put("/api/audiobooks/{audiobook_id}/playback")
async def save_playback_state(audiobook_id: str, payload: dict, authorization: str = Header(None)):
    """현재 계정의 오디오북 재생 상태를 최신 값으로 저장한다."""
    user_id = require_user_id(authorization)
    position, speed, repeat_mode = _validate_playback_state(payload)
    supabase = _supabase_or_503()
    state = {
        "user_id": user_id,
        "audiobook_id": audiobook_id,
        "current_time_seconds": position,
        "playback_speed": speed,
        "repeat_mode": repeat_mode,
        "last_played_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        response = supabase.table("playback_history").upsert(
            state, on_conflict="user_id,audiobook_id"
        ).execute()
        return response.data[0] if response.data else state
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"재생 상태 저장에 실패했습니다: {e}")


@app.delete("/api/audiobooks/{audiobook_id}")
async def delete_audiobook(audiobook_id: str, authorization: str = Header(None)):
    user_id = require_user_id(authorization)
    supabase = _supabase_or_503()

    try:
        # user_id를 조건에 포함해 남의 항목을 지울 수 없게 한다
        found = supabase.table("audiobooks").select("id") \
            .eq("id", audiobook_id).eq("user_id", user_id).execute().data
        if not found:
            raise HTTPException(status_code=404, detail="해당 오디오북을 찾을 수 없습니다.")

        audio_path, sentences_path = _object_paths(user_id, audiobook_id)
        try:
            supabase.storage.from_(AUDIOBOOK_BUCKET).remove([audio_path, sentences_path])
        except Exception:
            # 파일이 이미 없어도 행은 정리해야 한다
            pass

        supabase.table("audiobooks").delete() \
            .eq("id", audiobook_id).eq("user_id", user_id).execute()
        return {"deleted": audiobook_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"삭제에 실패했습니다: {e}")


# ====================================================
# P2: Authentication & User Management Routes
# ====================================================

@app.get("/api/auth/me")
async def get_current_user(authorization: str = Header(None)):
    """Get current user info from JWT token."""
    try:
        from auth import decode_token, get_supabase_client

        if not authorization:
            raise HTTPException(status_code=401, detail="No authorization token")

        # Extract token from "Bearer <token>"
        token = authorization.split(" ")[-1] if " " in authorization else authorization
        payload = decode_token(token)

        if not payload:
            raise HTTPException(status_code=401, detail="Invalid token")

        user_id = payload.get("sub")
        supabase = get_supabase_client(use_service_role=True)

        response = supabase.table("users").select("*").eq("id", user_id).single().execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="User not found")

        user = response.data
        return {
            "id": user["id"],
            "email": user["email"],
            "full_name": user.get("full_name"),
            "avatar_url": user.get("avatar_url"),
            "is_admin": (user.get("email") or "").lower() in _admin_emails(),
            "created_at": user.get("created_at")
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Get user error: {e}")
        raise HTTPException(status_code=401, detail="Unauthorized")

# ----------------------------------------------------
# 소셜 로그인
#
# 제공자를 늘릴 때 손댈 곳을 한 군데로 모은다: 토큰을 검증해 공통 프로필로
# 바꾸는 함수를 하나 쓰고 SOCIAL_VERIFIERS에 등록하면 된다. 사용자 조회/생성과
# 토큰 발급은 제공자와 무관하게 공유된다.
#
# 계정 식별은 이메일 기준이다. 같은 이메일로 다른 제공자를 쓰면 같은 계정이
# 된다(의도된 동작).
#
# NOTE: users 테이블에 google_id 컬럼이 제공자별로 박혀 있어 확장이 어렵다.
# 카카오/네이버/애플을 붙이기 전에 아래 마이그레이션을 권한다:
#   ALTER TABLE users ADD COLUMN provider VARCHAR(20);
#   ALTER TABLE users ADD COLUMN provider_id VARCHAR(255);
#   CREATE UNIQUE INDEX idx_users_provider ON users(provider, provider_id);
# 그 전까지는 google_id만 채우고 나머지 제공자는 이메일로만 식별한다.
# ----------------------------------------------------

def _verify_google(token_string: str) -> dict:
    """구글 ID 토큰을 검증해 공통 프로필로 변환한다."""
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token

    try:
        info = id_token.verify_oauth2_token(
            token_string, google_requests.Request(), os.getenv("GOOGLE_CLIENT_ID")
        )
    except Exception as e:
        print(f"Invalid Google token: {e}")
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")

    return {
        "provider": "google",
        "provider_id": info.get("sub"),
        "email": info.get("email"),
        "full_name": info.get("name", ""),
        "avatar_url": info.get("picture"),
    }


# 새 제공자는 검증 함수를 만들어 여기에 등록한다.
# 예: "kakao": _verify_kakao, "naver": _verify_naver, "apple": _verify_apple
SOCIAL_VERIFIERS = {
    "google": _verify_google,
}


def _upsert_social_user(profile: dict) -> dict:
    """제공자와 무관하게 사용자를 찾거나 만든다."""
    from auth import get_supabase_client

    email = profile.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="이메일을 가져오지 못했습니다.")

    supabase = get_supabase_client(use_service_role=True)
    if not supabase:
        raise HTTPException(status_code=503, detail="사용자 저장소에 연결할 수 없습니다.")

    try:
        found = supabase.table("users").select("*").eq("email", email).single().execute()
        existing = found.data
    except Exception:
        existing = None

    if existing:
        return existing

    user_id = str(uuid.uuid4())
    row = {
        "id": user_id,
        "email": email,
        "full_name": profile.get("full_name") or "",
        "avatar_url": profile.get("avatar_url"),
    }
    # 제공자별 식별자 컬럼은 구글만 존재한다. 위 NOTE의 마이그레이션 전까지는
    # 나머지 제공자의 식별자를 저장하지 않는다.
    if profile.get("provider") == "google":
        row["google_id"] = profile.get("provider_id")

    supabase.table("users").insert(row).execute()
    return row


@app.post("/api/auth/social/{provider}")
async def social_login(provider: str, data: dict):
    """소셜 로그인. 제공자별 검증 후 우리 JWT를 발급한다."""
    from auth import create_access_token

    verifier = SOCIAL_VERIFIERS.get(provider)
    if not verifier:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 로그인 방식입니다: {provider}")

    token_string = data.get("token")
    if not token_string:
        raise HTTPException(status_code=400, detail="토큰이 필요합니다.")

    try:
        profile = verifier(token_string)
        user = _upsert_social_user(profile)
        return {
            "access_token": create_access_token({"sub": user["id"]}),
            "token_type": "bearer",
            "user": {
                "id": user.get("id"),
                "email": user.get("email"),
                "full_name": user.get("full_name"),
                "avatar_url": user.get("avatar_url"),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Social login error ({provider}): {e}")
        raise HTTPException(status_code=500, detail="로그인에 실패했습니다.")

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


@app.on_event("startup")
async def startup_event():
    from auth import get_secret_key

    get_secret_key()
    asyncio.create_task(cleanup_expired_files_loop())
    asyncio.create_task(resume_background_synthesis_jobs())
    # 부팅 시에는 클라우드에 있으면 내려받기만 하고 합성은 하지 않는다.
    # 여기서 합성을 시작하면 공유 CPU 1개를 점유해 사용자 변환이 막힌다.
    # 클라우드에 없으면 상태를 pending으로 두고, 실제로 요청이 올 때
    # /api/default-book이 한 번만 생성한다(락으로 중복 방지).
    asyncio.create_task(prepare_default_book_from_cache())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
