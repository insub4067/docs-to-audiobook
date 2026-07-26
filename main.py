import os
import uuid
import docx
import pypdf
import asyncio
import html
import time
import re
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
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

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

# In-memory storage for extracted texts
# Keeps text temporarily for 30 minutes. Auto-expired by background task.
text_storage = {}

VOICE_METADATA = {
    "ko-KR-SunHiNeural": {
        "friendly_name": "선희 (차분한 뉴스/정보 전달 - 여성)",
        "description": "단정하고 차분하며, 정보 전달이나 지적인 낭독에 적합합니다."
    },
    "ko-KR-InJoonNeural": {
        "friendly_name": "인준 (신뢰감 있는 소설/다큐 - 남성)",
        "description": "진중하고 신뢰감 있는 남성 톤으로, 다큐멘터리나 소설 낭독에 적합합니다."
    },
    "ko-KR-JiMinNeural": {
        "friendly_name": "지민 (밝고 상냥한 동화/안내 - 여성)",
        "description": "밝고 친근하며, 동화책 낭독이나 상냥한 안내 멘트에 잘 어울립니다."
    },
    "ko-KR-SeoHyeonNeural": {
        "friendly_name": "서현 (부드러운 나레이션/뉴스 - 여성)",
        "description": "부드럽고 지적인 중저음 성우 스타일의 낭독입니다."
    },
    "ko-KR-SoonBokNeural": {
        "friendly_name": "순복 (편안하고 단정한 책 낭독 - 여성)",
        "description": "편안하고 정돈된 낭독으로, 긴 호흡의 책 읽기에 가장 편안합니다."
    },
    "ko-KR-YuJinNeural": {
        "friendly_name": "유진 (활기차고 경쾌한 대화 - 여성)",
        "description": "활기차고 생동감이 넘치며, 소설 속 대화체 구현에 뛰어납니다."
    },
    "ko-KR-HyunMinNeural": {
        "friendly_name": "현민 (생동감 있는 동화/라디오 - 남성)",
        "description": "생생하고 다이내믹하며, 아동 도서나 경쾌한 이야기에 적합합니다."
    }
}

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
    elif ext == ".txt":
        for encoding in ["utf-8", "cp949", "euc-kr", "utf-16", "latin-1"]:
            try:
                with open(file_path, "r", encoding=encoding) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
        raise HTTPException(status_code=400, detail="텍스트 파일 인코딩을 분석할 수 없습니다. UTF-8로 변환해 주세요.")
    else:
        raise HTTPException(status_code=400, detail="지원하지 않는 파일 형식입니다. (지원: .docx, .pdf, .txt)")

def preprocess_text(text: str) -> str:
    # 1. Clean line breaks: single newline to space, double newline to paragraph break with pause indicator
    cleaned_text = text.replace("\r\n", "\n")
    cleaned_text = cleaned_text.replace("\n\n", ".   ")
    cleaned_text = cleaned_text.replace("\n", " ")
    
    # 2. Clean consecutive spaces
    while "  " in cleaned_text:
        cleaned_text = cleaned_text.replace("  ", " ")
        
    return cleaned_text.strip()

def chunk_text(text: str, max_chars: int = 800) -> list:
    cleaned = preprocess_text(text)
    raw_sentences = re.split(r'(?<=[.!?])\s+', cleaned)
    
    chunks = []
    current_chunk = ""
    
    for sentence in raw_sentences:
        if not sentence:
            continue
        if len(current_chunk) + len(sentence) + 1 <= max_chars:
            if current_chunk:
                current_chunk += " " + sentence
            else:
                current_chunk = sentence
        else:
            if current_chunk:
                chunks.append(current_chunk)
            
            if len(sentence) > max_chars:
                for i in range(0, len(sentence), max_chars):
                    chunks.append(sentence[i:i+max_chars])
                current_chunk = ""
            else:
                current_chunk = sentence
                
    if current_chunk:
        chunks.append(current_chunk)
        
    return chunks

async def synthesize_chunk(chunk: str, voice: str, rate: str, pitch: str, semaphore: asyncio.Semaphore) -> bytes:
    async with semaphore:
        for attempt in range(3):
            try:
                communicate = edge_tts.Communicate(chunk, voice=voice, rate=rate, pitch=pitch)
                audio_data = b""
                async for msg in communicate.stream():
                    if msg.get("type") == "audio":
                        audio_data += msg.get("data")
                if audio_data:
                    return audio_data
            except Exception as e:
                print(f"Error in synthesize_chunk (attempt {attempt}): {e}")
                await asyncio.sleep(1)
        return b""

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
async def get_voices():
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
                
                filtered_voices.append({
                    "name": voice.get("Name", ""),
                    "short_name": short_name,
                    "gender": voice.get("Gender", ""),
                    "locale": lang,
                    "friendly_name": friendly_name,
                    "description": description
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

@app.post("/api/synthesize")
async def synthesize_text(
    text_id: str = Form(...),
    voice: str = Form("ko-KR-SunHiNeural"),
    rate: str = Form("+0%"),
    pitch: str = Form("+0Hz")
):
    if text_id not in text_storage:
        raise HTTPException(status_code=404, detail="요청한 텍스트 데이터를 찾을 수 없거나 만료되었습니다.")
    
    data = text_storage[text_id]
    text = data["text"]
        
    try:
        # 1. Split text into optimized chunks (800 chars limit)
        chunks = chunk_text(text, max_chars=800)
        if not chunks:
            raise HTTPException(status_code=400, detail="합성할 유효한 텍스트가 없습니다.")
            
        # 2. Semaphore to limit concurrent WSS connections to Microsoft (max 3)
        semaphore = asyncio.Semaphore(3)
        
        # 3. Create async tasks for each chunk
        tasks = [synthesize_chunk(chunk, voice, rate, pitch, semaphore) for chunk in chunks]
        
        # 4. Concurrently run synthesis tasks maintaining order
        audio_chunks = await asyncio.gather(*tasks)
        
        # 5. Merge all audio segments
        audio_data = b"".join(audio_chunks)
                
        if not audio_data:
            raise HTTPException(status_code=500, detail="음성 합성 결과가 비어 있습니다.")
            
        return Response(content=audio_data, media_type="audio/mpeg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS 오디오 생성 실패: {str(e)}")

# Serve static files (HTML, CSS, JS)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
async def read_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse(status_code=404, content={"message": "Frontend static file index.html not found. Build the frontend first."})

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
        except Exception as e:
            print(f"Error in cleanup background task: {e}")
        
        await asyncio.sleep(600) # Every 10 minutes

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(cleanup_expired_files_loop())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
