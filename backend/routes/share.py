"""공유 기능: 24시간 임시 서버 저장."""
import os
import re
import json
import time
import uuid
from fastapi import APIRouter, Request, UploadFile, File, Form, Header, HTTPException
from fastapi.responses import FileResponse

from state import SHARED_DIR, STATIC_DIR, require_user_id, enforce_rate_limit, save_upload_limited, _too_large
from routes.default_book import default_book_paths

router = APIRouter()

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


@router.post("/api/share")
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


@router.get("/api/share/{share_id}")
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


@router.get("/api/share/{share_id}/audio")
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


@router.get("/share/{share_id}")
async def serve_shared_page(share_id: str):
    """공유 링크로 접속 시 동일한 index.html 서빙 (JS가 URL을 파싱하여 Reader 모드 자동 진입)"""
    index_path = os.path.join(STATIC_DIR, "dist", "spa", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail="Page not found")
