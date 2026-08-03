"""구글 드라이브에서 문서 가져오기.

프론트가 Google Picker로 사용자가 고른 파일의 ID와, 그 세션에 한해
발급된 OAuth 액세스 토큰(scope: drive.file — 사용자가 직접 고른 파일만
접근 가능)을 보내면, 서버가 그 토큰으로 Drive API를 대신 호출해 내용을
받는다. 이 토큰은 이 요청 한 번에만 쓰고 서버에 저장하지 않는다.
"""
import os
import time
import uuid
import asyncio
import logging
import requests
from fastapi import APIRouter, Request, Header, HTTPException

from state import UPLOAD_DIR, upload_limit_for, synth_limit_for, text_storage, enforce_rate_limit, require_user_id
from text_processing import extract_text

router = APIRouter()
logger = logging.getLogger(__name__)

DRIVE_REQUEST_TIMEOUT_SEC = 30
SUPPORTED_BINARY_EXTENSIONS = {".docx", ".pdf", ".txt", ".md", ".markdown", ".hwp"}
GOOGLE_DOC_MIME = "application/vnd.google-apps.document"


@router.post("/api/import-drive-file")
async def import_drive_file(request: Request, payload: dict, authorization: str = Header(None)):
    require_user_id(authorization)
    enforce_rate_limit(request, "import_drive_file", limit=30, window_sec=600)

    file_id = (payload.get("file_id") or "").strip()
    drive_token = (payload.get("access_token") or "").strip()
    if not file_id or not drive_token:
        raise HTTPException(status_code=400, detail="가져올 파일 정보가 없습니다.")

    drive_headers = {"Authorization": f"Bearer {drive_token}"}

    try:
        meta_resp = await asyncio.to_thread(
            requests.get,
            f"https://www.googleapis.com/drive/v3/files/{file_id}",
            params={"fields": "name,mimeType,size"},
            headers=drive_headers,
            timeout=DRIVE_REQUEST_TIMEOUT_SEC,
        )
    except requests.RequestException:
        raise HTTPException(status_code=502, detail="구글 드라이브에 연결하지 못했습니다.")

    if meta_resp.status_code in (401, 403):
        raise HTTPException(status_code=401, detail="구글 드라이브 접근 권한이 만료되었습니다. 다시 시도해 주세요.")
    if not meta_resp.ok:
        logger.warning("Drive metadata fetch failed status=%s body=%s", meta_resp.status_code, meta_resp.text[:500])
        raise HTTPException(status_code=400, detail="드라이브 파일 정보를 가져오지 못했습니다.")

    meta = meta_resp.json()
    name = (meta.get("name") or "드라이브 문서").strip()
    mime_type = meta.get("mimeType", "")

    max_upload_bytes = upload_limit_for(authorization)
    try:
        size_bytes = int(meta.get("size") or 0)
    except (TypeError, ValueError):
        size_bytes = 0
    if size_bytes and size_bytes > max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"파일이 너무 큽니다. 최대 {max_upload_bytes // (1024 * 1024)}MB까지 지원합니다.",
        )

    try:
        if mime_type == GOOGLE_DOC_MIME:
            content_resp = await asyncio.to_thread(
                requests.get,
                f"https://www.googleapis.com/drive/v3/files/{file_id}/export",
                params={"mimeType": "text/plain"},
                headers=drive_headers,
                timeout=DRIVE_REQUEST_TIMEOUT_SEC,
            )
            if not content_resp.ok:
                logger.warning("Drive export failed status=%s body=%s", content_resp.status_code, content_resp.text[:500])
                raise HTTPException(status_code=400, detail="구글 문서를 내보내지 못했습니다.")
            text = content_resp.content.decode("utf-8", errors="replace")
            filename = name
        else:
            ext = os.path.splitext(name)[1].lower()
            if ext not in SUPPORTED_BINARY_EXTENSIONS:
                raise HTTPException(
                    status_code=400,
                    detail="지원하지 않는 파일 형식입니다. (지원: .docx, .pdf, .txt, .md, .hwp, 구글 문서)",
                )
            content_resp = await asyncio.to_thread(
                requests.get,
                f"https://www.googleapis.com/drive/v3/files/{file_id}",
                params={"alt": "media"},
                headers=drive_headers,
                timeout=DRIVE_REQUEST_TIMEOUT_SEC,
            )
            if not content_resp.ok:
                logger.warning("Drive download failed status=%s body=%s", content_resp.status_code, content_resp.text[:500])
                raise HTTPException(status_code=400, detail="드라이브 파일을 내려받지 못했습니다.")

            temp_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}_{os.path.basename(name)}")
            try:
                with open(temp_path, "wb") as f:
                    f.write(content_resp.content)
                text = await asyncio.to_thread(extract_text, temp_path, name)
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            filename = name
    except requests.RequestException:
        raise HTTPException(status_code=502, detail="구글 드라이브에서 파일을 받아오지 못했습니다.")
    except HTTPException:
        raise

    if not text.strip():
        raise HTTPException(status_code=400, detail="추출된 텍스트가 없습니다. 빈 파일이거나 읽을 수 없는 문서입니다.")

    max_synth_chars = synth_limit_for(max_upload_bytes)
    if len(text) > max_synth_chars:
        raise HTTPException(
            status_code=413,
            detail=f"텍스트가 너무 깁니다. 최대 {max_synth_chars:,}자까지 지원합니다.",
        )

    text_id = str(uuid.uuid4())
    text_storage[text_id] = {
        "filename": filename,
        "text": text,
        "char_count": len(text),
        "max_synth_chars": max_synth_chars,
        "created_at": time.time(),
        "access_token": uuid.uuid4().hex,
    }

    preview_len = min(500, len(text))
    return {
        "text_id": text_id,
        "filename": filename,
        "char_count": len(text),
        "preview": text[:preview_len] + ("..." if len(text) > preview_len else ""),
        "text_access_token": text_storage[text_id]["access_token"],
    }
