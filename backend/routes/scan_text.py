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

from state import (
    UPLOAD_DIR, synth_limit_for, upload_limit_for, save_upload_limited, text_storage,
    enforce_rate_limit, require_admin_user, scan_progress,
)

router = APIRouter()

MAX_IMAGE_BYTES = 15 * 1024 * 1024  # Vision API 자체 제한(20MB)보다 여유를 둔다
MAX_IMAGE_COUNT = 30  # 한 번에 연속 촬영해서 올릴 수 있는 최대 장수
MAX_PDF_BYTES = 50 * 1024 * 1024

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


PDF_OCR_RENDER_DPI = 300  # 200dpi는 작은 글자에서 인식률이 떨어져 300으로 올림


PDF_OCR_PAGE_CONCURRENCY = 5  # 합성 쪽 DOCUMENT_PART_CONCURRENCY와 같은 이유·같은 값


async def detect_pdf_text_via_ocr(pdf_path: str, on_progress=None) -> str:
    """스캔본 PDF(텍스트 레이어 없음) 폴백 — pypdf가 텍스트를 못 뽑을 때
    upload.py가 관리자 요청에 한해 호출한다. 페이지를 이미지로 렌더링해
    Vision에 넘긴다.

    페이지를 한 장씩 차례로 돌리면 30쪽 문서가 30번의 왕복을 직렬로 기다린다.
    페이지끼리는 서로 독립이므로 묶음으로 나눠 동시에 보낸다.

    ⚠️ 렌더링은 묶음 안에서도 순차다. PyMuPDF의 Document는 스레드 안전하지
    않아 같은 문서를 여러 스레드에서 그리면 죽는다. 어차피 오래 걸리는 쪽은
    Vision 왕복(네트워크)이라, 그것만 동시에 보내도 대부분을 회수한다.
    묶음 크기만큼만 PNG를 메모리에 들고 있게 되는 것도 이 방식의 이점이다 —
    전 페이지를 미리 렌더링하면 300dpi PNG가 통째로 램에 쌓인다.
    """
    import fitz  # PyMuPDF

    doc = fitz.open(pdf_path)
    try:
        total = doc.page_count
        if on_progress:
            on_progress(0, total)
        def render(start: int, end: int) -> list[bytes]:
            """⚠️ 반드시 to_thread로 부른다. 300dpi 렌더링은 CPU를 오래 잡아
            이벤트 루프에서 돌리면 그동안 서버가 다른 요청을 못 받는다."""
            return [
                doc[index].get_pixmap(dpi=PDF_OCR_RENDER_DPI).tobytes("png")
                for index in range(start, end)
            ]

        pages_text: list[str] = []
        for start in range(0, total, PDF_OCR_PAGE_CONCURRENCY):
            end = min(start + PDF_OCR_PAGE_CONCURRENCY, total)
            # 한 번에 한 스레드만 doc을 만진다(await로 직렬화) — fitz는 스레드 안전하지 않다.
            batch = await asyncio.to_thread(render, start, end)
            # gather는 넘긴 순서대로 결과를 돌려준다 — 페이지 순서가 유지된다.
            pages_text.extend(await asyncio.gather(
                *(asyncio.to_thread(_detect_document_text, png) for png in batch)
            ))
            if on_progress:
                on_progress(len(pages_text), total)
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


@router.post("/api/scan-pdf")
async def scan_pdf(
    request: Request,
    file: UploadFile = File(...),
    authorization: str = Header(None),
    scan_id: str = Header(None, alias="X-Scan-Id"),
):
    """"고성능 PDF" — pypdf를 거치지 않고 처음부터 PDF 전체를 Vision
    OCR로 처리한다(관리자 전용). 스캔본이 아니어도 pypdf보다 인식
    품질이 필요한 PDF를 위한 명시적 선택지.

    X-Scan-Id를 주면 처리하는 동안 진행 상황을 scan_progress에 남긴다.
    클라이언트는 GET /api/scan-progress/{scan_id}로 "몇 페이지 중 몇 장"을
    물어본다 — 이 응답은 다 끝나야 오므로 그 전에는 알 방법이 없다.
    """
    require_admin_user(authorization)
    enforce_rate_limit(request, "scan_pdf", limit=30, window_sec=600)

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF 파일만 업로드할 수 있습니다.")

    def report(done: int, total: int) -> None:
        if scan_id:
            scan_progress[scan_id] = {"done": done, "total": total}

    safe_name = os.path.basename(file.filename)
    temp_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}_{safe_name}")
    try:
        await save_upload_limited(file, temp_path, MAX_PDF_BYTES)
        try:
            text = await detect_pdf_text_via_ocr(temp_path, on_progress=report)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"텍스트 인식에 실패했습니다: {e}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        # 응답이 나가면 클라이언트가 더 물어볼 일이 없다. 남겨두면 프로세스가
        # 살아 있는 내내 쌓인다.
        scan_progress.pop(scan_id, None)

    if not text:
        raise HTTPException(status_code=400, detail="PDF에서 텍스트를 찾지 못했습니다.")

    max_upload_bytes = upload_limit_for(authorization)
    max_synth_chars = synth_limit_for(max_upload_bytes)
    if len(text) > max_synth_chars:
        raise HTTPException(
            status_code=413,
            detail=f"텍스트가 너무 깁니다. 최대 {max_synth_chars:,}자까지 지원합니다.",
        )

    text_id = str(uuid.uuid4())
    text_storage[text_id] = {
        "filename": safe_name,
        "text": text,
        "char_count": len(text),
        "max_synth_chars": max_synth_chars,
        "created_at": time.time(),
        "access_token": uuid.uuid4().hex,
    }

    preview_len = min(500, len(text))
    return {
        "text_id": text_id,
        "filename": safe_name,
        "char_count": len(text),
        "preview": text[:preview_len] + ("..." if len(text) > preview_len else ""),
        "text_access_token": text_storage[text_id]["access_token"],
    }


@router.get("/api/scan-progress/{scan_id}")
async def get_scan_progress(scan_id: str, authorization: str = Header(None)):
    """고성능 PDF가 몇 페이지까지 왔는지. 업로드 응답은 다 끝나야 오기 때문에,
    처리 중에 알려면 옆으로 물어보는 수밖에 없다.

    아직 첫 페이지를 그리기 전이거나 이미 끝났으면 빈 값을 준다 — 화면은
    그때 경과 시간만 보여주면 되므로 404로 실패시키지 않는다."""
    require_admin_user(authorization)
    progress = scan_progress.get(scan_id)
    if not progress:
        return {"done": None, "total": None}
    return {"done": progress["done"], "total": progress["total"]}
