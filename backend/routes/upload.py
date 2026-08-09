"""문서 업로드 → 텍스트 추출(미리보기)."""
import os
import uuid
import time
import asyncio
from fastapi import APIRouter, Request, UploadFile, File, Header, HTTPException
from fastapi.responses import JSONResponse

from state import (
    UPLOAD_DIR, upload_limit_for, synth_limit_for, MAX_UPLOAD_BYTES,
    large_admin_upload_lock, save_upload_limited, text_storage, enforce_rate_limit,
)
from text_processing import extract_text
from routes.scan_text import detect_pdf_text_via_ocr

router = APIRouter()


async def _pdf_ocr_fallback_text(temp_path: str, is_admin: bool, is_pdf: bool) -> str | None:
    """스캔본 PDF(텍스트 레이어 없음)라 pypdf가 텍스트를 못 뽑을 때의
    폴백. 관리자 PDF 요청에서만 시도하고, 실패하거나 대상이 아니면
    None을 돌려줘 호출부가 기존 에러 메시지를 그대로 쓰게 한다."""
    if not (is_admin and is_pdf and os.path.exists(temp_path)):
        return None
    try:
        text = await detect_pdf_text_via_ocr(temp_path)
        return text if text.strip() else None
    except Exception:
        return None


@router.post("/api/upload")
async def upload_file(request: Request, file: UploadFile = File(...), authorization: str = Header(None)):
    # 문서 텍스트 추출은 로그인 없이 가능 (미리보기 용도). 합성 시에만 차단.
    enforce_rate_limit(request, "upload", limit=100, window_sec=600)

    if not file.filename:
        raise HTTPException(status_code=400, detail="파일명이 존재하지 않습니다.")

    # 파일명이 경로에 그대로 들어가므로 디렉터리 성분을 제거한다
    safe_name = os.path.basename(file.filename)
    file_id = str(uuid.uuid4())
    temp_path = os.path.join(UPLOAD_DIR, f"{file_id}_{safe_name}")
    max_upload_bytes = upload_limit_for(authorization)
    max_synth_chars = synth_limit_for(max_upload_bytes)
    is_admin = max_upload_bytes > MAX_UPLOAD_BYTES
    is_pdf = safe_name.lower().endswith(".pdf")

    try:
        if max_upload_bytes > MAX_UPLOAD_BYTES:
            if large_admin_upload_lock.locked():
                raise HTTPException(
                    status_code=429,
                    detail="관리자 대용량 업로드는 하나씩 처리할 수 있습니다. 잠시 후 다시 시도해 주세요.",
                )
            async with large_admin_upload_lock:
                await save_upload_limited(file, temp_path, max_upload_bytes)
                text = await asyncio.to_thread(extract_text, temp_path, safe_name)
        else:
            await save_upload_limited(file, temp_path, max_upload_bytes)
            text = await asyncio.to_thread(extract_text, temp_path, safe_name)
    except HTTPException as original_error:
        fallback_text = await _pdf_ocr_fallback_text(temp_path, is_admin, is_pdf)
        if fallback_text is None:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            if is_pdf and not is_admin:
                return JSONResponse(status_code=400, content={
                    "detail": "이 PDF는 일반 방식으로 읽을 수 없습니다.",
                    "code": "pdf_ocr_required",
                })
            raise original_error
        text = fallback_text
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(status_code=500, detail=f"파일 임시 저장 중 에러가 발생했습니다: {str(e)}")

    # Extract text
    try:
        if not text.strip():
            fallback_text = await _pdf_ocr_fallback_text(temp_path, is_admin, is_pdf)
            if fallback_text is not None:
                text = fallback_text
            elif is_pdf and not is_admin:
                return JSONResponse(status_code=400, content={
                    "detail": "이 PDF는 일반 방식으로 읽을 수 없습니다.",
                    "code": "pdf_ocr_required",
                })
            else:
                raise HTTPException(status_code=400, detail="추출된 텍스트가 없습니다. 빈 파일이거나 읽을 수 없는 문서입니다.")

        if len(text) > max_synth_chars:
            raise HTTPException(
                status_code=413,
                detail=f"추출된 텍스트가 너무 깁니다. 최대 {max_synth_chars:,}자까지 지원합니다.",
            )

        # Save to memory storage with timestamp
        text_storage[file_id] = {
            "filename": file.filename,
            "text": text,
            "char_count": len(text),
            "max_synth_chars": max_synth_chars,
            "created_at": time.time(),
            "access_token": uuid.uuid4().hex,
        }

        # Return summary preview
        preview_len = min(500, len(text))
        return {
            "text_id": file_id,
            "filename": file.filename,
            "char_count": len(text),
            "preview": text[:preview_len] + ("..." if len(text) > preview_len else ""),
            "text_access_token": text_storage[file_id]["access_token"],
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"텍스트 추출 오류: {str(e)}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
