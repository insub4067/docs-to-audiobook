"""텍스트 직접 붙여넣기 → 텍스트 추출(미리보기).

파일 업로드와 같은 파이프라인(text_storage에 저장 후 동일한 응답 형식)을
쓰지만, 입력이 이미 텍스트라 파일 파싱 단계가 없다. 서버가 사용자 대신
외부로 요청을 나가지 않으므로(SSRF 위험 없음) 파일 업로드와 동일하게
로그인 없이도 미리보기까지 가능하다.
"""
import time
import uuid
from fastapi import APIRouter, Request, Header, HTTPException

from state import upload_limit_for, synth_limit_for, text_storage, enforce_rate_limit

router = APIRouter()


@router.post("/api/paste-text")
async def paste_text(request: Request, payload: dict, authorization: str = Header(None)):
    enforce_rate_limit(request, "upload", limit=100, window_sec=600)

    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="붙여넣은 텍스트가 없습니다.")

    title = (payload.get("title") or "").strip() or "붙여넣은 텍스트"

    max_upload_bytes = upload_limit_for(authorization)
    max_synth_chars = synth_limit_for(max_upload_bytes)
    if len(text) > max_synth_chars:
        raise HTTPException(
            status_code=413,
            detail=f"텍스트가 너무 깁니다. 최대 {max_synth_chars:,}자까지 지원합니다.",
        )

    file_id = str(uuid.uuid4())
    text_storage[file_id] = {
        "filename": title,
        "text": text,
        "char_count": len(text),
        "max_synth_chars": max_synth_chars,
        "created_at": time.time(),
        "access_token": uuid.uuid4().hex,
    }

    preview_len = min(500, len(text))
    return {
        "text_id": file_id,
        "filename": title,
        "char_count": len(text),
        "preview": text[:preview_len] + ("..." if len(text) > preview_len else ""),
        "text_access_token": text_storage[file_id]["access_token"],
    }
