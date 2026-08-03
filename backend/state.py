"""공용 상태·상수·헬퍼.

여러 라우트 모듈이 함께 쓰는 것만 여기 둔다. jobs/text_storage/_rate_buckets는
프로세스 전역 인메모리 상태라, 이 모듈을 통해서만 접근해야 여러 모듈이 같은
객체를 공유한다(각자 새로 만들면 안 된다).
"""
import os
import time
import shutil
import asyncio
from fastapi import HTTPException, Request, UploadFile


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
# static/은 프론트엔드 코드(vanilla JS/HTML/CSS + Vite 빌드 산출물)라
# frontend/ 아래 둔다. FastAPI는 서빙만 할 뿐이라 backend에서 상대 경로로
# 넘어가서 참조한다.
STATIC_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "frontend", "static"))
SHARED_DIR = os.path.join(BASE_DIR, "shared")
# 합성이 끝난 오디오를 클라이언트가 받아갈 때까지 잠시 두는 곳
JOB_AUDIO_DIR = os.path.join(BASE_DIR, "job_audio")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(SHARED_DIR, exist_ok=True)
os.makedirs(JOB_AUDIO_DIR, exist_ok=True)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024

MAX_ADMIN_UPLOAD_BYTES = 250 * 1024 * 1024

MAX_SYNTH_CHARS = 100_000

MAX_ADMIN_SYNTH_CHARS = 50_000_000

AUDIO_BYTES_PER_CHAR_ESTIMATE = 903
DISK_ESTIMATE_SAFETY_FACTOR = 2
# 이 디스크를 다른 업로드·공유 파일과도 나눠 쓰므로 항상 이만큼은 비워둔다.
DISK_RESERVE_BYTES = 1 * 1024 ** 3

DOCUMENT_PART_CONCURRENCY = 5

large_admin_upload_lock = asyncio.Lock()

background_synthesis_lock = asyncio.Lock()

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

def resolve_job_owner(authorization: str, anonymous_session: str) -> str:
    if authorization:
        return require_user_id(authorization)

    session_id = (anonymous_session or "").strip()
    if len(session_id) < 16 or len(session_id) > 128:
        raise HTTPException(status_code=401, detail="로그인 또는 체험 세션이 필요합니다.")
    return f"anonymous:{session_id}"

def require_job_owner(job_id: str, authorization: str, anonymous_session: str) -> dict:
    user_id = resolve_job_owner(authorization, anonymous_session)
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="해당 작업을 찾을 수 없습니다.")
    if job.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="이 작업에 접근할 권한이 없습니다.")
    return job

def _supabase_or_503():
    from auth import get_supabase_client

    client = get_supabase_client(use_service_role=True)
    if not client:
        raise HTTPException(status_code=503, detail="클라우드 저장소에 연결할 수 없습니다.")
    return client

def require_admin_user(authorization: str) -> str:
    """환경변수 허용 목록에 등록된 사용자만 관리자 통계를 볼 수 있게 한다."""
    user_id = require_user_id(authorization)
    allowed_emails = _admin_emails()
    if not allowed_emails:
        raise HTTPException(status_code=403, detail="관리자 계정이 설정되지 않았습니다.")

    supabase = _supabase_or_503()
    try:
        user = supabase.table("users").select("email").eq("id", user_id).maybe_single().execute().data
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"관리자 권한을 확인하지 못했습니다: {e}")
    if not user or (user.get("email") or "").lower() not in allowed_emails:
        raise HTTPException(status_code=403, detail="관리자만 접근할 수 있습니다.")
    return user_id

def _admin_emails() -> set[str]:
    return {
        email.strip().lower()
        for email in os.getenv("ADMIN_EMAILS", "").split(",")
        if email.strip()
    }

def upload_limit_for(authorization: str | None) -> int:
    """관리자로 검증된 요청에만 대용량 파일 상한을 적용한다."""
    if not authorization:
        return MAX_UPLOAD_BYTES
    try:
        require_admin_user(authorization)
    except HTTPException:
        return MAX_UPLOAD_BYTES
    return MAX_ADMIN_UPLOAD_BYTES

def synth_limit_for(upload_limit_bytes: int) -> int:
    return (
        MAX_ADMIN_SYNTH_CHARS
        if upload_limit_bytes == MAX_ADMIN_UPLOAD_BYTES
        else MAX_SYNTH_CHARS
    )

def _has_enough_disk_for_synthesis(char_count: int) -> bool:
    """지금 이 문서를 합성해도 디스크가 안 찰지, 고정 상한 대신 그 순간의
    실제 여유 공간을 재서 판단한다."""
    estimated_bytes = char_count * AUDIO_BYTES_PER_CHAR_ESTIMATE * DISK_ESTIMATE_SAFETY_FACTOR
    free_bytes = shutil.disk_usage(JOB_AUDIO_DIR).free
    return estimated_bytes <= free_bytes - DISK_RESERVE_BYTES

def _object_paths(user_id: str, audiobook_id: str):
    """오디오와 문장 데이터를 나란히 둔다. audiobooks 테이블에 sentences
    컬럼이 없어 스키마 변경 없이 버킷에 함께 보관한다."""
    base = f"{user_id}/{audiobook_id}"
    return f"{base}.mp3", f"{base}.sentences.json"

def _validate_folder_ownership(supabase, user_id: str, folder_id: str) -> None:
    """folder_id가 이 사용자 소유인지 확인한다. 아니면 404.

    audiobooks.py(즉시 생성)와 tts.py(백그라운드 작업 큐 등록)가 함께 쓴다."""
    found = supabase.table("folders").select("id") \
        .eq("id", folder_id).eq("user_id", user_id).execute().data
    if not found:
        raise HTTPException(status_code=404, detail="폴더를 찾을 수 없습니다.")

APP_BUILD_ID = str(int(time.time()))

text_storage = {}

jobs = {}
