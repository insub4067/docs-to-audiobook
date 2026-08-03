"""이미지에서 텍스트 스캔(OCR) — 관리자 전용, 추후 유료 사용자에게 개방 예정.

구글 Cloud Vision API의 document_text_detection을 쓴다. Cloud TTS와 같은
서비스 계정 자격증명(GOOGLE_APPLICATION_CREDENTIALS_JSON)을 재사용한다 —
그 서비스 계정이 속한 GCP 프로젝트에서 Vision API가 활성화돼 있어야 한다.
"""
import os
import json
import time
import uuid
import asyncio
from fastapi import APIRouter, Request, UploadFile, File, Header, HTTPException

from state import synth_limit_for, upload_limit_for, text_storage, enforce_rate_limit, require_admin_user

router = APIRouter()

MAX_IMAGE_BYTES = 15 * 1024 * 1024  # Vision API 자체 제한(20MB)보다 여유를 둔다
MAX_IMAGE_COUNT = 30  # 한 번에 연속 촬영해서 올릴 수 있는 최대 장수

_vision_client = None


def _get_vision_client():
    global _vision_client
    if _vision_client is None:
        from google.cloud import vision

        creds_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
        if creds_json:
            # google_tts_adapter.py와 동일한 방식 — 파일 마운트 없이
            # 환경변수로만 자격증명을 넣는 배포 환경(Fly.io) 대응.
            from google.oauth2 import service_account

            info = json.loads(creds_json)
            credentials = service_account.Credentials.from_service_account_info(info)
            _vision_client = vision.ImageAnnotatorClient(credentials=credentials)
        else:
            _vision_client = vision.ImageAnnotatorClient()
    return _vision_client


def _detect_document_text(content: bytes) -> str:
    """동기 호출 — asyncio.to_thread로 감싸 쓴다. 테스트에서 패치하기
    쉽도록 실제 Vision 호출을 이 함수 하나로 모은다."""
    from google.cloud import vision

    client = _get_vision_client()
    image = vision.Image(content=content)
    response = client.document_text_detection(image=image)
    if response.error.message:
        raise RuntimeError(response.error.message)
    return (response.full_text_annotation.text or "").strip()


def detect_pdf_text_via_ocr(pdf_path: str) -> str:
    """스캔본 PDF(텍스트 레이어 없음) 폴백 — pypdf가 텍스트를 못 뽑을 때
    upload.py가 관리자 요청에 한해 호출한다. 페이지를 이미지로 렌더링해
    한 장씩 Vision에 넘긴다. 동기 함수라 asyncio.to_thread로 감싸 쓴다."""
    import fitz  # PyMuPDF

    doc = fitz.open(pdf_path)
    try:
        pages_text = []
        for page in doc:
            pixmap = page.get_pixmap(dpi=200)
            pages_text.append(_detect_document_text(pixmap.tobytes("png")))
        return "\n\n".join(t for t in pages_text if t)
    finally:
        doc.close()


@router.post("/api/scan-text")
async def scan_text(request: Request, files: list[UploadFile] = File(...), authorization: str = Header(None)):
    require_admin_user(authorization)
    enforce_rate_limit(request, "scan_text", limit=30, window_sec=600)

    if not files:
        raise HTTPException(status_code=400, detail="이미지 파일이 없습니다.")
    if len(files) > MAX_IMAGE_COUNT:
        raise HTTPException(status_code=413, detail=f"한 번에 최대 {MAX_IMAGE_COUNT}장까지 스캔할 수 있습니다.")

    # 촬영한 순서(페이지 순서)를 그대로 유지해 순서대로 이어붙인다.
    page_texts: list[str] = []
    for image_file in files:
        content = await image_file.read()
        if not content:
            raise HTTPException(status_code=400, detail="이미지 파일이 비어 있습니다.")
        if len(content) > MAX_IMAGE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"이미지가 너무 큽니다. 최대 {MAX_IMAGE_BYTES // (1024 * 1024)}MB까지 지원합니다.",
            )
        try:
            page_text = await asyncio.to_thread(_detect_document_text, content)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"텍스트 인식에 실패했습니다: {e}")
        if page_text:
            page_texts.append(page_text)

    text = "\n\n".join(page_texts)
    if not text:
        raise HTTPException(status_code=400, detail="이미지에서 텍스트를 찾지 못했습니다.")

    max_upload_bytes = upload_limit_for(authorization)
    max_synth_chars = synth_limit_for(max_upload_bytes)
    if len(text) > max_synth_chars:
        raise HTTPException(
            status_code=413,
            detail=f"텍스트가 너무 깁니다. 최대 {max_synth_chars:,}자까지 지원합니다.",
        )

    text_id = str(uuid.uuid4())
    page_label = f" ({len(files)}장)" if len(files) > 1 else ""
    filename = f"스캔한 텍스트{page_label} {time.strftime('%Y-%m-%d %H:%M')}"
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
