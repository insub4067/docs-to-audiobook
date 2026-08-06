"""경제 뉴스·라이브러리 등록 작업의 공통 골격과 관리자 조회 API.

이 테이블이 있는 이유는 원문(source_text)을 합성 전에 저장하기 위해서다.
예전에는 합성이 실패하면 audiobooks 행이 아예 만들어지지 않아 서버 로그
말고는 아무 흔적도 남지 않았고, 관리자는 무엇이 왜 실패했는지 알 수도
다시 시도할 수도 없었다. 항목이 두세 개일 때는 넘어갈 수 있지만 경전이나
뉴스를 여러 개 등록하면 조용히 빠진 항목을 찾을 방법이 없다.

뉴스와 라이브러리는 "제목 + 본문 + 메타데이터를 TTS로 합성해 audiobooks에
넣는다"는 점이 같아서 kind로만 구분하고 같은 테이블·같은 처리 경로를 쓴다.
"""
import logging
import uuid
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException

from state import _supabase_or_503, require_admin_user

router = APIRouter()
logger = logging.getLogger(__name__)

CONTENT_JOB_KINDS = ("news", "library")

# 진행률은 DB가 아니라 프로세스 메모리에만 둔다 — 청크마다 UPDATE를 날리면
# 긴 경전 하나에 수백 번의 쓰기가 생긴다. 재시작하면 사라지지만 그때는
# status(DB)가 진실이고, 진행률은 아예 안 보여주면 된다(0%로 보여주면
# 멈춘 것처럼 오해한다).
_job_progress: dict[str, int] = {}


def progress_callback_for(job_id: str):
    """synthesize_document에 넘길 진행률 콜백."""
    def on_progress(done: int, total: int) -> None:
        if total:
            _job_progress[job_id] = round(done * 100 / total)
    return on_progress


def queue_jobs(supabase, kind: str, admin_user_id: str, items: list[dict]) -> list[str]:
    """합성을 시작하기 전에 원문을 먼저 저장한다. title/content를 뺀 나머지는
    통째로 metadata에 담아 두었다가 완성될 때 audiobooks 컬럼으로 옮긴다."""
    job_ids = []
    for item in items:
        job_id = str(uuid.uuid4())
        supabase.table("content_jobs").insert({
            "id": job_id,
            "kind": kind,
            "admin_user_id": admin_user_id,
            "title": item["title"],
            "source_text": item["content"],
            "metadata": {key: value for key, value in item.items() if key not in ("title", "content")},
        }).execute()
        job_ids.append(job_id)
    return job_ids


def _store_handler(kind: str):
    """kind별 저장 함수. 순환 import를 피하려고 호출 시점에 가져온다."""
    if kind == "news":
        from routes.news import store_news_item
        return store_news_item
    from routes.library import store_library_item
    return store_library_item


async def _run_one(supabase, job_id: str) -> dict | None:
    try:
        response = supabase.table("content_jobs").select("*").eq("id", job_id).maybe_single().execute()
    except Exception:
        logger.exception("등록 작업을 불러오지 못했습니다 job_id=%s", job_id)
        return None
    if not response or not response.data:
        return None
    job = response.data

    supabase.table("content_jobs").update({"status": "processing", "error": None}).eq("id", job_id).execute()
    _job_progress[job_id] = 0
    try:
        item = {"title": job["title"], "content": job["source_text"], **(job.get("metadata") or {})}
        audiobook_id = await _store_handler(job["kind"])(supabase, job["admin_user_id"], item, job_id)
        # 완성됐으면 작업 기록은 지운다 — 남겨두면 "등록 작업" 목록이 완료
        # 항목으로 계속 불어나고, 같은 콘텐츠가 아래 목록에도 있어 두 번 보인다.
        supabase.table("content_jobs").delete().eq("id", job_id).execute()
        return {"id": audiobook_id, "title": job["title"]}
    except Exception as error:
        logger.exception("콘텐츠 등록 실패 kind=%s title=%s", job.get("kind"), job.get("title"))
        supabase.table("content_jobs").update({
            "status": "error",
            "error": f"{type(error).__name__}: {error}"[:500],
        }).eq("id", job_id).execute()
        return None
    finally:
        _job_progress.pop(job_id, None)


async def run_jobs(job_ids: list[str]) -> list[dict]:
    """작업을 차례로 처리하고 성공한 항목만 돌려준다."""
    supabase = _supabase_or_503()
    created = []
    for job_id in job_ids:
        result = await _run_one(supabase, job_id)
        if result:
            created.append(result)
    return created


@router.get("/api/admin/content-jobs")
async def list_content_jobs(authorization: str = Header(None)):
    """진행 중이거나 실패한 등록 작업. 성공한 작업은 행을 지우므로 여기 없다."""
    require_admin_user(authorization)
    supabase = _supabase_or_503()
    try:
        # source_text는 작품 한 편 분량이라 목록 응답에 싣지 않는다.
        rows = supabase.table("content_jobs") \
            .select("id, kind, title, status, error, created_at") \
            .order("created_at", desc=True).limit(50).execute().data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"등록 작업을 불러오지 못했습니다: {e}")
    for row in rows:
        row["progress"] = _job_progress.get(row["id"])
    return {"jobs": rows}


@router.post("/api/admin/content-jobs/{job_id}/retry")
async def retry_content_job(job_id: str, background_tasks: BackgroundTasks, authorization: str = Header(None)):
    """실패한 작업을 원문에서 다시 시작한다. 배포 중 재시작 등으로
    'processing'에 멈춰 버린 작업도 되살릴 수 있도록 상태를 가리지 않는다 —
    원문이 남아 있는 한 다시 만드는 건 언제나 안전하다."""
    require_admin_user(authorization)
    supabase = _supabase_or_503()
    try:
        response = supabase.table("content_jobs").select("id").eq("id", job_id).maybe_single().execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"작업을 확인하지 못했습니다: {e}")
    if not response or not response.data:
        raise HTTPException(status_code=404, detail="등록 작업을 찾을 수 없습니다.")

    supabase.table("content_jobs").update({"status": "queued", "error": None}).eq("id", job_id).execute()
    background_tasks.add_task(run_jobs, [job_id])
    return {"status": "queued"}


@router.delete("/api/admin/content-jobs/{job_id}")
async def delete_content_job(job_id: str, authorization: str = Header(None)):
    """다시 시도하지 않을 실패 작업을 목록에서 치운다."""
    require_admin_user(authorization)
    supabase = _supabase_or_503()
    try:
        supabase.table("content_jobs").delete().eq("id", job_id).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"작업을 삭제하지 못했습니다: {e}")
    return {"deleted": job_id}
