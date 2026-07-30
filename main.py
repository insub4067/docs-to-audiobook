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
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Response, BackgroundTasks, Header
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.background import BackgroundTask
import edge_tts
import mimetypes
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("application/javascript", ".js")

app = FastAPI(title="Docs to Audiobook Converter - Hybrid")

# CORS middleware for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Directories config
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
STATIC_DIR = os.path.join(BASE_DIR, "static")
SHARED_DIR = os.path.join(BASE_DIR, "shared")
# 합성이 끝난 오디오를 클라이언트가 받아갈 때까지 잠시 두는 곳
JOB_AUDIO_DIR = os.path.join(BASE_DIR, "job_audio")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(SHARED_DIR, exist_ok=True)
os.makedirs(JOB_AUDIO_DIR, exist_ok=True)

# App build ID: generated once at server startup.
# Changes on every redeploy (new process start), used by client to detect updates.
APP_BUILD_ID = str(int(time.time()))

# In-memory storage for extracted texts
# Keeps text temporarily for 30 minutes. Auto-expired by background task.
text_storage = {}

# In-memory storage for synthesis jobs
# Tracks the status of background edge-tts generation tasks
jobs = {}

VOICE_METADATA = {
    "ko-KR-SunHiNeural": {
        "friendly_name": "선희 (차분한 뉴스/정보 전달 - 여성)",
        "description": "단정하고 차분하며, 정보 전달이나 지적인 낭독에 적합합니다.",
        "tone": "formal", "use_case": ["news", "education", "documentation"]
    },
    "ko-KR-InJoonNeural": {
        "friendly_name": "인준 (신뢰감 있는 소설/다큐 - 남성)",
        "description": "진중하고 신뢰감 있는 남성 톤으로, 다큐멘터리나 소설 낭독에 적합합니다.",
        "tone": "serious", "use_case": ["fiction", "documentary"]
    },
    "ko-KR-JiMinNeural": {
        "friendly_name": "지민 (밝고 상냥한 동화/안내 - 여성)",
        "description": "밝고 친근하며, 동화책 낭독이나 상냥한 안내 멘트에 잘 어울립니다.",
        "tone": "friendly", "use_case": ["children", "guide", "instruction"]
    },
    "ko-KR-SeoHyeonNeural": {
        "friendly_name": "서현 (부드러운 나레이션/뉴스 - 여성)",
        "description": "부드럽고 지적인 중저음 성우 스타일의 낭독입니다.",
        "tone": "soft", "use_case": ["narration", "news", "meditation"]
    },
    "ko-KR-SoonBokNeural": {
        "friendly_name": "순복 (편안하고 단정한 책 낭독 - 여성)",
        "description": "편안하고 정돈된 낭독으로, 긴 호흡의 책 읽기에 가장 편안합니다.",
        "tone": "comfortable", "use_case": ["novel", "audiobook", "long_text"]
    },
    "ko-KR-YuJinNeural": {
        "friendly_name": "유진 (활기차고 경쾌한 대화 - 여성)",
        "description": "활기차고 생동감이 넘치며, 소설 속 대화체 구현에 뛰어납니다.",
        "tone": "energetic", "use_case": ["dialogue", "drama", "entertainment"]
    },
    "ko-KR-HyunMinNeural": {
        "friendly_name": "현민 (생동감 있는 동화/라디오 - 남성)",
        "description": "생생하고 다이내믹하며, 아동 도서나 경쾌한 이야기에 적합합니다.",
        "tone": "dynamic", "use_case": ["children", "radio", "entertainment"]
    }
}

def extract_hwp_text(filepath: str) -> str:
    try:
        import olefile
        import zlib
        import struct

        f = olefile.OleFileIO(filepath)
        dirs = f.listdir()
        if ['FileHeader'] not in dirs:
            return ""
        header = f.openstream('FileHeader').read()
        is_compressed = (header[36] & 1) != 0

        sections = [d for d in dirs if d[0] == 'BodyText']
        text_chunks = []
        for sec in sections:
            stream = f.openstream(sec).read()
            if is_compressed:
                stream = zlib.decompress(stream, -15)
            
            i = 0
            while i < len(stream):
                if i + 4 > len(stream):
                    break
                header_val = struct.unpack('<I', stream[i:i+4])[0]
                rec_type = header_val & 0x3FF
                rec_len = (header_val >> 20) & 0xFFF
                if rec_len == 0xFFF:
                    if i + 8 > len(stream):
                        break
                    rec_len = struct.unpack('<I', stream[i+4:i+8])[0]
                    i += 8
                else:
                    i += 4
                
                if rec_type == 67:  # HWPTAG_PARA_TEXT
                    data = stream[i:i+rec_len]
                    text = data.decode('utf-16le', errors='ignore')
                    # Remove HWP control characters / inline objects
                    clean_chars = [c for c in text if ord(c) >= 32 or c in ('\n', '\r', '\t')]
                    text_chunks.append("".join(clean_chars))
                i += rec_len
        return "\n".join(text_chunks)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"HWP 파일 해석 실패: {str(e)}")

def extract_text(file_path: str, filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".docx":
        doc = docx.Document(file_path)
        return "\n".join([para.text for para in doc.paragraphs])
    elif ext == ".pdf":
        reader = pypdf.PdfReader(file_path)
        text_list = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text_list.append(t)
        return "\n".join(text_list)
    elif ext in [".txt", ".md", ".markdown"]:
        for encoding in ["utf-8", "cp949", "euc-kr", "utf-16", "latin-1"]:
            try:
                with open(file_path, "r", encoding=encoding) as f:
                    content = f.read()
                    return content
            except UnicodeDecodeError:
                continue
        raise HTTPException(status_code=400, detail="텍스트 파일 인코딩을 분석할 수 없습니다. UTF-8로 변환해 주세요.")
    elif ext == ".hwp":
        text = extract_hwp_text(file_path)
        if not text.strip():
            raise HTTPException(status_code=400, detail="HWP 파일에서 텍스트를 추출할 수 없습니다.")
        return text
    else:
        raise HTTPException(status_code=400, detail="지원하지 않는 파일 형식입니다. (지원: .docx, .pdf, .txt, .md, .hwp)")

def preprocess_text(text: str) -> str:
    # 1. Clean line breaks: single newline to space, double newline to paragraph break with pause indicator
    cleaned_text = text.replace("\r\n", "\n")
    
    # 2. Prevent headings from merging with the next paragraph
    lines = cleaned_text.split('\n')
    for i in range(len(lines)):
        line = lines[i].strip()
        # If the line is a markdown heading, ensure it ends with a period so TTS treats it as a separate sentence
        if re.match(r'^(#{1,6})', line) and not line.endswith('.'):
            lines[i] = line + "."
    cleaned_text = '\n'.join(lines)

    cleaned_text = cleaned_text.replace("\n\n", ".   ")
    cleaned_text = cleaned_text.replace("\n", " ")
    
    # 3. Clean consecutive spaces
    while "  " in cleaned_text:
        cleaned_text = cleaned_text.replace("  ", " ")
        
    return cleaned_text.strip()


def extract_markdown_headings(raw_text: str) -> list:
    """Parse markdown headings from original text before TTS cleaning.
    Returns a list of {cleaned_text, level, display_text} dicts.
    """
    headings = []
    for line in raw_text.split('\n'):
        stripped = line.strip()
        if not stripped:
            continue

        # Match # Heading, ## Heading, ### Heading
        m = re.match(r'^(#{1,3})\s+(.+)$', stripped)
        if m:
            level = len(m.group(1))
            display = re.sub(r'[*_~`\\]', '', m.group(2)).strip()
            cleaned = clean_tts_text(m.group(2))
            if cleaned:
                headings.append({
                    "cleaned_text": cleaned,
                    "display_text": display,
                    "level": level
                })
            continue
    return headings


def annotate_sentences_with_headings(sentences: list, headings: list) -> tuple:
    """Match TTS sentences to extracted headings and annotate them.
    Returns (annotated_sentences, matched_headings_for_index).
    """
    heading_index = []
    remaining_headings = list(headings)  # copy so we can consume matches

    for i, s in enumerate(sentences):
        s_text = s["text"].strip()
        matched = False

        # Only check the next 3 headings to maintain order and allow for at most 2 skipped headings
        for h in remaining_headings[:3]:
            h_text = h["cleaned_text"].strip()
            
            # Remove all punctuation and spaces for a super robust match.
            # This handles cases where TTS splits "1. Title" into "1" and "Title".
            s_super_clean = re.sub(r'[^\w가-힣]', '', s_text)
            h_super_clean = re.sub(r'[^\w가-힣]', '', h_text)

            is_match = False
            if s_super_clean == h_super_clean:
                is_match = True
            elif h_super_clean in s_super_clean:
                is_match = True
            elif s_super_clean in h_super_clean and len(s_super_clean) >= len(h_super_clean) * 0.5:
                # If s_text is a substring of the heading, it must be at least half its length 
                # to prevent short random words/punctuation from stealing the heading.
                is_match = True

            if is_match:
                s["type"] = "heading"
                s["level"] = h["level"]
                s["display"] = h["display_text"]
                heading_index.append({
                    "text": h["display_text"],
                    "level": h["level"],
                    "sentIndex": i,
                    "startMs": s["start"]
                })
                remaining_headings.remove(h)
                matched = True
                break

        if not matched:
            s["type"] = "text"

    return sentences, heading_index


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="파일명이 존재하지 않습니다.")
    
    file_id = str(uuid.uuid4())
    temp_path = os.path.join(UPLOAD_DIR, f"{file_id}_{file.filename}")
    
    # Save uploaded file
    try:
        with open(temp_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"파일 임시 저장 중 에러가 발생했습니다: {str(e)}")
    
    # Extract text
    try:
        text = extract_text(temp_path, file.filename)
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
        if not text.strip():
            raise HTTPException(status_code=400, detail="추출된 텍스트가 없습니다. 빈 파일이거나 읽을 수 없는 문서입니다.")
        
        # Save to memory storage with timestamp
        text_storage[file_id] = {
            "filename": file.filename,
            "text": text,
            "char_count": len(text),
            "created_at": time.time()
        }
        
        # Return summary preview
        preview_len = min(500, len(text))
        return {
            "text_id": file_id,
            "filename": file.filename,
            "char_count": len(text),
            "preview": text[:preview_len] + ("..." if len(text) > preview_len else "")
        }
    except HTTPException as he:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise he
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(status_code=500, detail=f"텍스트 추출 오류: {str(e)}")

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
            if lang.startswith("ko-KR") or lang.startswith("en-US"):
                short_name = voice.get("ShortName", "")

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

        # Sort so Korean voices are at the top
        filtered_voices.sort(key=lambda x: 0 if x["locale"].startswith("ko-KR") else 1)
        return filtered_voices
    except Exception as e:
        # Fallback list if edge-tts call fails or no internet
        return [
            {"name": "Microsoft Server Speech Text to Speech Voice (ko-KR, SunHiNeural)", "short_name": "ko-KR-SunHiNeural", "gender": "Female", "locale": "ko-KR", "friendly_name": "선희 (차분한 뉴스/정보 전달 - 여성)", "description": "단정하고 차분하며, 정보 전달이나 지적인 낭독에 적합합니다."},
            {"name": "Microsoft Server Speech Text to Speech Voice (ko-KR, InJoonNeural)", "short_name": "ko-KR-InJoonNeural", "gender": "Male", "locale": "ko-KR", "friendly_name": "인준 (신뢰감 있는 소설/다큐 - 남성)", "description": "진중하고 신뢰감 있는 남성 톤으로, 다큐멘터리나 소설 낭독에 적합합니다."},
            {"name": "Microsoft Server Speech Text to Speech Voice (ko-KR, JiMinNeural)", "short_name": "ko-KR-JiMinNeural", "gender": "Female", "locale": "ko-KR", "friendly_name": "지민 (밝고 상냥한 동화/안내 - 여성)", "description": "밝고 친근하며, 동화책 낭독이나 상냥한 안내 멘트에 잘 어울립니다."}
        ]

def clean_tts_text(text: str) -> str:
    # 1. 마크다운 특수문자 제거 (#, *, _, ~, `, \, > 등)
    t = re.sub(r'#+\s*', '', text)
    t = re.sub(r'[*_~`\\]', '', t)
    t = re.sub(r'>\s*', '', t)
    
    # 2. 한글 뒤 괄호 안의 영문(원문 표기) 제거: 예) 스캔들(A Scandal in Bohemia) -> 스캔들
    # 한글 문자나 숫자 바로 뒤에 오는 (영어/공백/문장부호) 괄호 패턴 제거
    t = re.sub(r'([가-힣0-9])\s*\([A-Za-z0-9\s.,\-\'\"]+\)', r'\1', t)
    
    # 3. 연속 공백 정리
    t = re.sub(r'\s+', ' ', t).strip()
    return t

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
                audio_data = b""
                sentences = []
                async for msg in communicate.stream():
                    if msg.get("type") == "audio":
                        audio_data += msg.get("data")
                    elif msg.get("type") == "SentenceBoundary":
                        offset_ms = msg.get("offset", 0) // 10000
                        duration_ms = msg.get("duration", 0) // 10000
                        sentences.append({
                            "text": msg.get("text", ""),
                            "start": offset_ms,
                            "end": offset_ms + duration_ms
                        })
            if audio_data:
                return chunk_index, audio_data, sentences
            last_error = RuntimeError("빈 오디오 응답을 받았습니다.")
        except Exception as e:
            last_error = e

        if attempt < max_attempts - 1:
            await asyncio.sleep(1.5 * (attempt + 1))

    raise last_error

async def synthesize_document(raw_text: str, voice: str, rate: str, pitch: str) -> tuple:
    """Synthesize a full document into (audio_bytes, annotated_sentences, heading_index)."""
    # Extract heading metadata from original text (before preprocessing strips newlines)
    headings = extract_markdown_headings(raw_text)

    # Preprocess text for TTS (merge lines, clean spacing)
    text = preprocess_text(raw_text)

    # Split text into chunks (~800 chars per chunk for optimal parallel TTS generation)
    paragraphs = text.split(". ")
    chunks = []
    current_chunk = ""

    for p in paragraphs:
        if len(current_chunk) + len(p) < 800:
            current_chunk += (p + ". ")
        else:
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            current_chunk = p + ". "
    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    if not chunks:
        chunks = [text]

    # Process all chunks concurrently using asyncio.gather
    tasks = [
        synthesize_chunk(i, chunk, voice, rate, pitch)
        for i, chunk in enumerate(chunks)
    ]
    results = await asyncio.gather(*tasks)

    # Sort by chunk index to maintain exact order
    results.sort(key=lambda x: x[0])

    combined_audio = b""
    combined_sentences = []
    current_time_offset = 0

    for idx, audio_data, sentences in results:
        combined_audio += audio_data

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

    # Annotate sentences with heading metadata
    annotated_sentences, heading_index = annotate_sentences_with_headings(
        combined_sentences, headings
    )

    return combined_audio, annotated_sentences, heading_index


async def process_synthesis_task(job_id: str, raw_text: str, voice: str, rate: str, pitch: str):
    try:
        combined_audio, annotated_sentences, heading_index = await synthesize_document(
            raw_text, voice, rate, pitch
        )

        if not combined_audio:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = "음성 합성 결과가 비어 있습니다."
            return

        # 완성된 오디오는 디스크로 내린다. base64로 메모리에 들고 있으면
        # 문자당 약 900바이트 x 1.33배가 클라이언트가 가져갈 때까지 RAM에
        # 남아, 동시 작업 수만큼 곱해져 인스턴스가 죽는다.
        audio_path = os.path.join(JOB_AUDIO_DIR, f"{job_id}.mp3")
        with open(audio_path, "wb") as f:
            f.write(combined_audio)
        del combined_audio

        jobs[job_id]["audio_path"] = audio_path
        jobs[job_id]["sentences"] = annotated_sentences
        jobs[job_id]["headings"] = heading_index
        jobs[job_id]["status"] = "completed"

    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)


@app.post("/api/synthesize")
async def synthesize_text(
    background_tasks: BackgroundTasks,
    text_id: str = Form(...),
    voice: str = Form("ko-KR-SunHiNeural"),
    rate: str = Form("+0%"),
    pitch: str = Form("+0Hz")
):
    if text_id not in text_storage:
        raise HTTPException(status_code=404, detail="요청한 텍스트 데이터를 찾을 수 없거나 만료되었습니다.")
    
    data = text_storage[text_id]
    raw_text = data["text"]
    
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status": "processing",
        "audio_path": None,
        "sentences": [],
        "headings": [],
        "error": None,
        "created_at": time.time()
    }
    
    # Pass raw text — process_synthesis_task handles preprocessing internally
    background_tasks.add_task(process_synthesis_task, job_id, raw_text, voice, rate, pitch)
    
    return {"job_id": job_id}

@app.get("/api/job/{job_id}")
async def get_job_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="해당 작업을 찾을 수 없습니다.")
        
    job = jobs[job_id]

    if job["status"] == "completed":
        # 오디오는 별도 엔드포인트에서 파일로 스트리밍한다. 여기서는
        # 메타데이터만 주고 job은 남겨둔다(오디오를 받아가야 정리된다).
        return JSONResponse(content={
            "status": "completed",
            "audio_url": f"/api/job/{job_id}/audio",
            "sentences": job["sentences"],
            "headings": job.get("headings", [])
        })

    return JSONResponse(content={"status": job["status"], "error": job.get("error")})


@app.get("/api/job/{job_id}/audio")
async def get_job_audio(job_id: str):
    job = jobs.get(job_id)
    if not job or job.get("status") != "completed":
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

# --------------------------------------------------
# Share Feature: 24-hour temporary server storage
# --------------------------------------------------

@app.post("/api/share")
async def create_share(
    audio: UploadFile = File(...),
    title: str = Form(...),
    sentences: str = Form(...),
    headings: str = Form("[]")
):
    """클라이언트가 오디오북을 공유할 때 서버에 임시 저장 (24시간 후 자동 삭제)"""
    share_id = str(uuid.uuid4())[:12]
    share_dir = os.path.join(SHARED_DIR, share_id)
    os.makedirs(share_dir, exist_ok=True)

    # Save audio file
    audio_path = os.path.join(share_dir, "audio.mp3")
    with open(audio_path, "wb") as f:
        content = await audio.read()
        f.write(content)

    # Save metadata
    meta = {
        "title": title,
        "sentences": json.loads(sentences),
        "headings": json.loads(headings),
        "created_at": time.time()
    }
    meta_path = os.path.join(share_dir, "meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)

    return {"share_id": share_id}

@app.get("/api/share/{share_id}")
async def get_share_meta(share_id: str):
    """공유된 오디오북의 메타데이터 (제목 + 문장 타이밍) 반환"""
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
DEFAULT_BOOK_SOURCE = os.path.join(STATIC_DIR, "samples", "sherlock-holmes.md")
DEFAULT_BOOK_TITLE = "셜록 홈즈의 모험"
DEFAULT_BOOK_VOICE = "ko-KR-SunHiNeural"

default_book_state = {"status": "pending", "error": None}
default_book_lock = asyncio.Lock()


def default_book_paths():
    return (
        os.path.join(DEFAULT_BOOK_DIR, "audio.mp3"),
        os.path.join(DEFAULT_BOOK_DIR, "meta.json"),
    )


async def generate_default_book():
    """기본 제공 오디오북을 생성해 디스크에 캐시한다. 이미 있으면 재사용."""
    audio_path, meta_path = default_book_paths()

    if os.path.exists(audio_path) and os.path.exists(meta_path):
        default_book_state["status"] = "ready"
        print("Default audiobook already exists on disk. Skipping generation.")
        return

    if not os.path.exists(DEFAULT_BOOK_SOURCE):
        default_book_state["status"] = "error"
        default_book_state["error"] = "기본 제공 문서를 찾을 수 없습니다."
        print(f"Default book source missing: {DEFAULT_BOOK_SOURCE}")
        return

    default_book_state["status"] = "generating"
    print(f"Starting default audiobook generation from {DEFAULT_BOOK_SOURCE}...")
    try:
        raw_text = extract_text(DEFAULT_BOOK_SOURCE, "sherlock-holmes.md")
        audio_bytes, sentences, headings = await synthesize_document(
            raw_text, DEFAULT_BOOK_VOICE, "+0%", "+0Hz"
        )

        if not audio_bytes:
            raise RuntimeError("음성 합성 결과가 비어 있습니다.")

        os.makedirs(DEFAULT_BOOK_DIR, exist_ok=True)
        with open(audio_path, "wb") as f:
            f.write(audio_bytes)
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump({
                "title": DEFAULT_BOOK_TITLE,
                "sentences": sentences,
                "headings": headings,
                "char_count": len(raw_text),
                "size_bytes": len(audio_bytes),
            }, f, ensure_ascii=False)

        default_book_state["status"] = "ready"
        default_book_state["error"] = None
        print(f"Default book generated: {len(audio_bytes)} bytes")
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

    if default_book_state["status"] == "error":
        async def retry_generation():
            async with default_book_lock:
                if default_book_state["status"] == "error":
                    await generate_default_book()
        asyncio.create_task(retry_generation())
        # Let the client know we are retrying
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
    })


@app.get("/api/default-book/audio")
async def get_default_book_audio():
    audio_path, _ = default_book_paths()
    if not os.path.exists(audio_path):
        raise HTTPException(status_code=404, detail="기본 제공 오디오북이 아직 준비되지 않았습니다.")
    return FileResponse(audio_path, media_type="audio/mpeg", filename="sherlock-holmes.mp3")


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
# P2: Authentication & User Management Routes
# ====================================================

@app.post("/api/auth/register")
async def register(user_data: dict):
    """Register a new user."""
    try:
        from auth import get_supabase_client, hash_password
        from models import UserRegister

        supabase = get_supabase_client(use_service_role=True)
        if not supabase:
            raise HTTPException(status_code=500, detail="Database connection failed")

        # Parse request
        email = user_data.get("email")
        password = user_data.get("password")
        full_name = user_data.get("full_name")

        if not email or not password:
            raise HTTPException(status_code=400, detail="Email and password required")

        # Check if user exists
        try:
            existing = supabase.table("users").select("id").eq("email", email).single().execute()
            raise HTTPException(status_code=409, detail="Email already registered")
        except:
            pass  # User doesn't exist, continue

        # Create user
        hashed_pw = hash_password(password)
        response = supabase.table("users").insert({
            "email": email,
            "password_hash": hashed_pw,
            "full_name": full_name
        }).execute()

        if response.data:
            return {"status": "success", "message": "User registered successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to create user")

    except HTTPException:
        raise
    except Exception as e:
        print(f"Registration error: {e}")
        raise HTTPException(status_code=500, detail="Registration failed")

@app.post("/api/auth/login")
async def login(credentials: dict):
    """Login user with email and password."""
    try:
        from auth import get_supabase_client, verify_password, create_access_token

        supabase = get_supabase_client(use_service_role=True)
        if not supabase:
            raise HTTPException(status_code=500, detail="Database connection failed")

        email = credentials.get("email")
        password = credentials.get("password")

        if not email or not password:
            raise HTTPException(status_code=400, detail="Email and password required")

        # Get user from database
        response = supabase.table("users").select("*").eq("email", email).single().execute()

        if not response.data:
            raise HTTPException(status_code=401, detail="Invalid email or password")

        user = response.data
        if not verify_password(password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid email or password")

        # Create JWT token
        token = create_access_token({"sub": user["id"]})

        return {
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": user["id"],
                "email": user["email"],
                "full_name": user.get("full_name"),
                "avatar_url": user.get("avatar_url")
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Login error: {e}")
        raise HTTPException(status_code=500, detail="Login failed")

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
            "created_at": user.get("created_at")
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Get user error: {e}")
        raise HTTPException(status_code=401, detail="Unauthorized")

@app.post("/api/auth/google")
async def google_login(data: dict):
    """Login/Register with Google OAuth token."""
    try:
        from auth import get_supabase_client, create_access_token
        from google.auth.transport import requests
        from google.oauth2 import id_token

        token_string = data.get("token")
        if not token_string:
            raise HTTPException(status_code=400, detail="Token required")

        try:
            idinfo = id_token.verify_oauth2_token(
                token_string,
                requests.Request(),
                os.getenv("GOOGLE_CLIENT_ID")
            )
        except Exception as e:
            print(f"Invalid Google token: {e}")
            raise HTTPException(status_code=401, detail="Invalid token")

        email = idinfo.get("email")
        name = idinfo.get("name", "")
        google_id = idinfo.get("sub")

        if not email:
            raise HTTPException(status_code=400, detail="Email not found in token")

        supabase = get_supabase_client(use_service_role=True)

        try:
            user = supabase.table("users").select("*").eq("email", email).single().execute()
            existing_user = user.data
        except:
            existing_user = None

        if existing_user:
            user_id = existing_user["id"]
            user_response = existing_user
        else:
            user_id = str(uuid.uuid4())
            supabase.table("users").insert({
                "id": user_id,
                "email": email,
                "full_name": name,
                "password_hash": "",
                "google_id": google_id,
                "avatar_url": idinfo.get("picture", None)
            }).execute()
            user_response = {
                "id": user_id,
                "email": email,
                "full_name": name,
                "avatar_url": idinfo.get("picture", None),
                "created_at": datetime.utcnow().isoformat()
            }

        token = create_access_token({"sub": user_id})

        return {
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": user_response.get("id"),
                "email": user_response.get("email"),
                "full_name": user_response.get("full_name"),
                "avatar_url": user_response.get("avatar_url")
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Google login error: {e}")
        raise HTTPException(status_code=500, detail="Google login failed")

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(cleanup_expired_files_loop())
    asyncio.create_task(generate_default_book())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
