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
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Response, BackgroundTasks, Header, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.background import BackgroundTask
from supertonic import TTS
import soundfile as sf
import numpy as np
import io
import mimetypes
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("application/javascript", ".js")

app = FastAPI(title="Docs to Audiobook Converter - Hybrid")

# 프론트엔드는 같은 출처에서 상대 경로로만 API를 호출하므로 와일드카드가
# 필요 없다. allow_origins=["*"] 와 allow_credentials=True 조합은 잘못된
# 설정이기도 하다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://docs-to-audiobook.onrender.com",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
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

# ---- 리소스 상한 ----
# 업로드는 지금까지 클라이언트에서만 검사했다. API를 직접 호출하면 그대로
# 통과해 파일 전체가 메모리에 올라간다.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

# 합성 문자 수 상한. 오디오는 문자당 약 903바이트이고 합성 피크는 그 2배쯤
# 되므로, 10MB 텍스트(약 350만 자)를 그대로 받으면 오디오만 2.9GB가 되어
# 반드시 죽는다. 10만 자면 약 4시간 분량이라 실사용에는 충분하다.
MAX_SYNTH_CHARS = 100_000

# 글로벌 Supertonic 엔진 초기화 (부팅 시 모델 다운로드)
print("Initializing Supertonic TTS engine...")
tts_engine = TTS(auto_download=True)
print("TTS engine initialized.")


# 공유되는 오디오는 오디오북 전체라 크다. MAX_SYNTH_CHARS(10만 자) 분량이
# 약 90MB이므로 여유를 둔다. 대신 메모리에 담지 않고 디스크로 흘려보낸다.
MAX_SHARE_AUDIO_BYTES = 120 * 1024 * 1024


def _too_large(max_bytes: int) -> HTTPException:
    return HTTPException(
        status_code=413,
        detail=f"파일이 너무 큽니다. 최대 {max_bytes // (1024 * 1024)}MB까지 지원합니다."
    )


async def read_upload_limited(upload: UploadFile, max_bytes: int) -> bytes:
    """상한을 넘으면 즉시 중단한다. 전체를 읽고 나서 검사하면 이미 늦다."""
    parts = []
    total = 0
    while True:
        chunk = await upload.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise _too_large(max_bytes)
        parts.append(chunk)
    return b"".join(parts)


async def save_upload_limited(upload: UploadFile, dest_path: str, max_bytes: int) -> int:
    """업로드를 메모리에 모으지 않고 곧바로 파일에 쓴다."""
    total = 0
    try:
        with open(dest_path, "wb") as f:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise _too_large(max_bytes)
                f.write(chunk)
    except HTTPException:
        # 상한 초과 시 쓰다 만 파일을 남기지 않는다
        try:
            os.remove(dest_path)
        except OSError:
            pass
        raise
    return total


# ---- 레이트 리밋 ----
# 모든 콘텐츠 엔드포인트가 무인증이라 합성 요청을 무제한으로 받을 수 있다.
# 단일 인스턴스라 인메모리 슬라이딩 윈도우로 충분하다.
_rate_buckets = {}

def enforce_rate_limit(request: Request, name: str, limit: int, window_sec: int):
    ip = request.client.host if request.client else "unknown"
    key = (name, ip)
    now = time.time()
    hits = [t for t in _rate_buckets.get(key, []) if now - t < window_sec]
    if len(hits) >= limit:
        raise HTTPException(
            status_code=429,
            detail="요청이 너무 잦습니다. 잠시 후 다시 시도해 주세요."
        )
    hits.append(now)
    _rate_buckets[key] = hits


# ---- 클라우드 보관함 ----
AUDIOBOOK_BUCKET = "audiobooks"
# 서명 URL 유효시간. 다운로드는 큰 파일이라 넉넉히 준다.
SIGNED_URL_TTL = 3600


def require_user_id(authorization: str) -> str:
    """Bearer 토큰에서 user_id를 꺼낸다. 없거나 잘못되면 401."""
    from auth import decode_token

    if not authorization:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    token = authorization.split(" ")[-1] if " " in authorization else authorization
    payload = decode_token(token)
    if not payload or not payload.get("sub"):
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")
    return payload["sub"]


def _supabase_or_503():
    from auth import get_supabase_client

    client = get_supabase_client(use_service_role=True)
    if not client:
        raise HTTPException(status_code=503, detail="클라우드 저장소에 연결할 수 없습니다.")
    return client


def _object_paths(user_id: str, audiobook_id: str):
    """오디오와 문장 데이터를 나란히 둔다. audiobooks 테이블에 sentences
    컬럼이 없어 스키마 변경 없이 버킷에 함께 보관한다."""
    base = f"{user_id}/{audiobook_id}"
    return f"{base}.ogg", f"{base}.sentences.json"


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
async def upload_file(request: Request, file: UploadFile = File(...), authorization: str = Header(None)):
    # 문서 텍스트 추출은 로그인 없이 가능 (미리보기 용도). 합성 시에만 차단.
    enforce_rate_limit(request, "upload", limit=100, window_sec=600)

    if not file.filename:
        raise HTTPException(status_code=400, detail="파일명이 존재하지 않습니다.")

    # 파일명이 경로에 그대로 들어가므로 디렉터리 성분을 제거한다
    safe_name = os.path.basename(file.filename)
    file_id = str(uuid.uuid4())
    temp_path = os.path.join(UPLOAD_DIR, f"{file_id}_{safe_name}")

    # Save uploaded file
    try:
        content = await read_upload_limited(file, MAX_UPLOAD_BYTES)
        with open(temp_path, "wb") as buffer:
            buffer.write(content)
        del content
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"파일 임시 저장 중 에러가 발생했습니다: {str(e)}")

    # Extract text
    try:
        text = extract_text(temp_path, safe_name)
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
    voices = []
    
    # Supertonic 한국어 지원 보이스 매핑
    # F1~F5 (여성), M1~M5 (남성)
    for i in range(1, 6):
        voices.append({
            "name": f"Supertonic Female {i}",
            "short_name": f"F{i}",
            "gender": "Female",
            "locale": "ko-KR",
            "friendly_name": f"슈퍼토닉 여성 음성 {i}",
            "description": "매우 자연스러운 다국어 여성 성우",
            "tone": "soft",
            "use_case": ["novel", "audiobook"]
        })
        voices.append({
            "name": f"Supertonic Male {i}",
            "short_name": f"M{i}",
            "gender": "Male",
            "locale": "ko-KR",
            "friendly_name": f"슈퍼토닉 남성 음성 {i}",
            "description": "매우 자연스러운 다국어 남성 성우",
            "tone": "formal",
            "use_case": ["documentary", "news"]
        })
        
    # tone/use_case 필터링
    if tone:
        voices = [v for v in voices if v.get("tone") == tone]
    if use_case:
        voices = [v for v in voices if use_case in v.get("use_case", [])]
        
    return voices

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

def synthesize_supertonic_sync(text: str, voice: str, rate: float):
    """동기적으로 TTS를 실행하고 (wav_array, duration, text)를 반환"""
    # M1, F1 등 기본 내장된 목소리 스킨
    style = tts_engine.get_voice_style(voice_name=voice)
    # 텍스트 합성 수행
    wav_array, duration = tts_engine.synthesize(text, voice_style=style, lang="ko", speed=rate)
    return wav_array, duration, text

async def synthesize_document(raw_text: str, voice: str, rate: str, pitch: str, audio_path: str) -> tuple:
    """Synthesize a full document into audio_path sequentially to save memory."""
    headings = extract_markdown_headings(raw_text)
    text = preprocess_text(raw_text)

    # Split text into chunks (~800 chars per chunk)
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

    # Convert rate string to float
    speed_float = 1.0
    if isinstance(rate, str) and rate.endswith("%"):
        if rate.startswith("+"):
            speed_float = 1.0 + float(rate[1:-1])/100.0
        elif rate.startswith("-"):
            speed_float = 1.0 - float(rate[1:-1])/100.0

    combined_sentences = []
    current_time_offset = 0
    
    # 디스크에 OGG 스트림으로 바로 기록 (메모리 OOM 방지)
    with sf.SoundFile(audio_path, mode='w', samplerate=44100, channels=1, format='OGG') as f:
        for chunk in chunks:
            tts_text = clean_tts_text(chunk)
            if not tts_text:
                tts_text = chunk
                
            # 쓰레드 풀에서 동기 TTS 작업 실행
            wav_array, duration, processed_text = await asyncio.to_thread(
                synthesize_supertonic_sync, tts_text, voice, speed_float
            )
            
            # OGG 파일에 Append
            f.write(wav_array)
            
            # 타임스탬프 계산 (문장 단위)
            combined_sentences.append({
                "text": processed_text,
                "start": current_time_offset,
                "end": current_time_offset + int(duration * 1000)
            })
            
            current_time_offset += int(duration * 1000)
            
            # GC 해제 (OOM 방지)
            del wav_array

    # Annotate sentences with heading metadata
    annotated_sentences, heading_index = annotate_sentences_with_headings(
        combined_sentences, headings
    )

    return True, annotated_sentences, heading_index


async def process_synthesis_task(job_id: str, raw_text: str, voice: str, rate: str, pitch: str):
    try:
        audio_path = os.path.join(JOB_AUDIO_DIR, f"{job_id}.ogg")
        success, annotated_sentences, heading_index = await synthesize_document(
            raw_text, voice, rate, pitch, audio_path
        )

        if not success:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = "음성 합성 결과가 비어 있습니다."
            return

        jobs[job_id]["audio_path"] = audio_path
        jobs[job_id]["sentences"] = annotated_sentences
        jobs[job_id]["headings"] = heading_index
        jobs[job_id]["status"] = "completed"

    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)


@app.post("/api/synthesize")
async def synthesize_text(
    request: Request,
    background_tasks: BackgroundTasks,
    text_id: str = Form(...),
    voice: str = Form("ko-KR-HyunsuMultilingualNeural"),
    rate: str = Form("+5%"),
    pitch: str = Form("+0Hz"),
    authorization: str = Header(None)
):
    require_user_id(authorization)
    # 가장 비싼 엔드포인트다. 배치 8개를 여러 번 돌릴 여유는 남긴다.
    enforce_rate_limit(request, "synthesize", limit=40, window_sec=600)

    if text_id not in text_storage:
        raise HTTPException(status_code=404, detail="요청한 텍스트 데이터를 찾을 수 없거나 만료되었습니다.")

    data = text_storage[text_id]
    raw_text = data["text"]

    if len(raw_text) > MAX_SYNTH_CHARS:
        raise HTTPException(
            status_code=413,
            detail=f"문서가 너무 깁니다. 최대 {MAX_SYNTH_CHARS:,}자까지 변환할 수 있습니다 "
                   f"(현재 {len(raw_text):,}자)."
        )

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
        media_type="audio/ogg",
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

    share_id = str(uuid.uuid4())[:12]
    share_dir = os.path.join(SHARED_DIR, share_id)
    os.makedirs(share_dir, exist_ok=True)

    # Save audio file
    audio_path = os.path.join(share_dir, "audio.mp3")
    await save_upload_limited(audio, audio_path, MAX_SHARE_AUDIO_BYTES)

    # Save metadata
    meta = {
        "title": title,
        "sentences": json.loads(sentences),
        "headings": json.loads(headings),
        "created_at": time.time(),
        "never_expire": title == "셜록 홈즈의 모험"
    }
    meta_path = os.path.join(share_dir, "meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)

    return {"share_id": share_id}

@app.get("/api/share/{share_id}")
async def get_share_meta(share_id: str):
    """공유된 오디오북의 메타데이터 (제목 + 문장 타이밍) 반환"""
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
DEFAULT_BOOK_SOURCE = os.path.join(STATIC_DIR, "samples", "sherlock-holmes.md")
DEFAULT_BOOK_TITLE = "셜록 홈즈의 모험"
DEFAULT_BOOK_VOICE = "ko-KR-HyunsuMultilingualNeural"

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
        _, sentences, headings = await synthesize_document(
            raw_text, DEFAULT_BOOK_VOICE, "+5%", "+0Hz", audio_path
        )

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
    return FileResponse(audio_path, media_type="audio/ogg", filename="sherlock-holmes.ogg")

@app.get("/api/audio/{job_id}.ogg")
async def download_audiobook(job_id: str):
    audio_path = os.path.join(JOB_AUDIO_DIR, f"{job_id}.ogg")
    if not os.path.exists(audio_path):
        raise HTTPException(status_code=404, detail="Audio file not found")
        
    return FileResponse(audio_path, media_type="audio/ogg")


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
                            if not meta.get("never_expire", False) and now - meta.get("created_at", 0) > 86400:  # 24 hours
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

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(cleanup_expired_files_loop())
    asyncio.create_task(generate_default_book())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
