"""라이브러리: 공개 이용 가능한 경전·철학서·고전문학을 관리자가 등록해
개인 문서/경제 뉴스와 같은 파이프라인(TTS 합성 → Storage 저장)으로
오디오북화한다. 완성된 작품은 별도 테이블 없이 audiobooks를 재사용하고
is_library로 구분한다. 다만 합성이 끝나기 전까지의 등록 작업은
library_jobs에 따로 남긴다 — 원문을 들고 있어야 실패한 작품을 다시
만들 수 있기 때문이다.

문서 자체보다 중요한 제약: library_status가 'review'(기본값)인 동안은
공개 목록/상세에서 절대 노출하지 않는다. 판본별 저작권이 실제로
확인되기 전까지 공개하지 않는다는 원칙(오래된 원전이라고 저절로
자유 이용은 아님) 때문이다. 관리자가 직접 확인한 뒤에만 'published'로
등록하거나 바꿔야 한다 — AI가 대신 "확인됨"이라고 표시하게 하지 않는다.
"""
import json
import logging
import uuid
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException

from state import _supabase_or_503, require_admin_user, require_user_id, AUDIOBOOK_BUCKET, _object_paths
from routes.audiobooks import audiobook_items_with_urls
from routes.tts import synthesize_document
from tts_providers.voice_catalog import DEFAULT_VOICE_KEY

router = APIRouter()
logger = logging.getLogger(__name__)

LIBRARY_STATUSES = {"review", "published"}

# 등록 작업이 원문과 함께 넘겨받는 메타데이터 키. 합성이 끝나면
# audiobooks의 library_* 컬럼으로 옮겨간다.
LIBRARY_JOB_METADATA_KEYS = ("category", "edition", "translator", "source", "rights", "description", "status")

# 진행률은 DB가 아니라 프로세스 메모리에만 둔다 — 청크마다 UPDATE를 날리면
# 긴 경전 하나에 수백 번의 쓰기가 생긴다. 재시작하면 사라지지만 그때는
# status(DB)가 진실이고, 진행률은 0부터 다시 보이면 그만이다.
_job_progress: dict[str, int] = {}


def _parse_library_payload(raw_text: str) -> list[dict]:
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        items = json.loads(text)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="올바른 JSON 형식이 아닙니다.")

    if not isinstance(items, list) or not items:
        raise HTTPException(status_code=400, detail="작품 배열이 비어 있습니다.")

    parsed = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or "").strip()
        content = (item.get("content") or "").strip()
        if not title or not content:
            continue
        status = item.get("status") if item.get("status") in LIBRARY_STATUSES else "review"
        parsed.append({
            "title": title[:255],
            "content": content,
            "category": (item.get("category") or "").strip()[:50] or None,
            "edition": (item.get("edition") or "").strip()[:255] or None,
            "translator": (item.get("translator") or "").strip()[:255] or None,
            "source": (item.get("source") or "").strip()[:255] or None,
            "rights": (item.get("rights") or "").strip() or None,
            "description": (item.get("description") or "").strip() or None,
            "status": status,
        })

    if not parsed:
        raise HTTPException(status_code=400, detail="title/content가 있는 작품이 없습니다.")
    return parsed


async def _store_library_item(supabase, admin_user_id: str, item: dict, job_id: str | None = None) -> str:
    def on_progress(done: int, total: int) -> None:
        if job_id and total:
            _job_progress[job_id] = round(done * 100 / total)

    audio_bytes, sentences, _headings = await synthesize_document(
        item["content"], DEFAULT_VOICE_KEY, "+5%", "+0Hz", progress_callback=on_progress
    )
    if not audio_bytes:
        raise RuntimeError("음성 합성 결과가 비어 있습니다.")

    audiobook_id = str(uuid.uuid4())
    audio_path, sentences_path = _object_paths(admin_user_id, audiobook_id)
    storage = supabase.storage.from_(AUDIOBOOK_BUCKET)
    storage.upload(audio_path, audio_bytes, {"content-type": "audio/mpeg"})
    try:
        storage.upload(
            sentences_path,
            json.dumps(sentences, ensure_ascii=False).encode("utf-8"),
            {"content-type": "application/json"},
        )
    except Exception:
        storage.remove([audio_path])
        raise

    # 목록 카드에 재생시간/장 수를 보여주려고 미리 계산해 둔다 — 매번
    # sentences 파일을 내려받아 계산하면 목록 화면이 N배 느려진다.
    duration_seconds = round(max((s.get("end", 0) for s in sentences), default=0) / 1000)
    chapter_count = sum(1 for s in sentences if s.get("type") == "heading")

    supabase.table("audiobooks").insert({
        "id": audiobook_id,
        "user_id": admin_user_id,
        "title": item["title"],
        "file_name": item["title"],
        "storage_path": audio_path,
        "duration_seconds": duration_seconds,
        "is_library": True,
        "library_status": item["status"],
        "library_category": item["category"],
        "library_edition": item["edition"],
        "library_translator": item["translator"],
        "library_source": item["source"],
        "library_rights": item["rights"],
        "library_description": item["description"],
        "library_chapter_count": chapter_count,
    }).execute()
    return audiobook_id


async def _run_library_job(supabase, job_id: str) -> None:
    """작업 한 건을 원문에서 되살려 처리한다. 최초 등록과 재시도가 같은
    경로를 쓰도록 DB에서 다시 읽는다 — 재시도 때만 도는 별도 코드가 있으면
    한쪽만 고쳐진 채로 남는다."""
    try:
        response = supabase.table("library_jobs").select("*").eq("id", job_id).maybe_single().execute()
    except Exception:
        logger.exception("등록 작업을 불러오지 못했습니다 job_id=%s", job_id)
        return
    if not response or not response.data:
        return
    job = response.data

    supabase.table("library_jobs").update({"status": "processing", "error": None}).eq("id", job_id).execute()
    _job_progress[job_id] = 0
    try:
        metadata = job.get("metadata") or {}
        item = {
            "title": job["title"],
            "content": job["source_text"],
            **{key: metadata.get(key) for key in LIBRARY_JOB_METADATA_KEYS},
        }
        item["status"] = item["status"] if item["status"] in LIBRARY_STATUSES else "review"
        await _store_library_item(supabase, job["admin_user_id"], item, job_id)
        # 작품이 만들어졌으면 작업 기록은 지운다 — 남겨두면 "등록 작업"
        # 목록이 완료 항목으로 계속 불어나고, 같은 작품이 아래 "등록된
        # 작품 관리"에도 있어 두 번 보인다.
        supabase.table("library_jobs").delete().eq("id", job_id).execute()
    except Exception as error:
        logger.exception("라이브러리 작품 등록 실패 title=%s", job.get("title"))
        supabase.table("library_jobs").update({
            "status": "error",
            "error": f"{type(error).__name__}: {error}"[:500],
        }).eq("id", job_id).execute()
    finally:
        _job_progress.pop(job_id, None)


async def _process_library_batch(job_ids: list[str]) -> None:
    supabase = _supabase_or_503()
    for job_id in job_ids:
        await _run_library_job(supabase, job_id)


@router.post("/api/admin/library")
async def add_library_items(payload: dict, background_tasks: BackgroundTasks, authorization: str = Header(None)):
    admin_user_id = require_admin_user(authorization)
    items = _parse_library_payload(payload.get("text") or "")

    # 합성을 시작하기 전에 원문을 먼저 저장한다. 예전에는 실패하면 아무
    # 흔적도 남지 않아(작품 행은 합성 성공 후에야 생겼다) 무엇이 왜 실패했는지
    # 알 수도, 다시 시도할 수도 없었다.
    supabase = _supabase_or_503()
    job_ids = []
    for item in items:
        job_id = str(uuid.uuid4())
        supabase.table("library_jobs").insert({
            "id": job_id,
            "admin_user_id": admin_user_id,
            "title": item["title"],
            "source_text": item["content"],
            "metadata": {key: item[key] for key in LIBRARY_JOB_METADATA_KEYS},
        }).execute()
        job_ids.append(job_id)

    background_tasks.add_task(_process_library_batch, job_ids)
    return {"queued": len(job_ids)}


# ⚠️ /api/admin/library/{audiobook_id}(PATCH)와 경로가 겹치므로 작업 라우트를
# 먼저 등록한다. library_saves 때 겪은 것과 같은 종류의 함정이다.
@router.get("/api/admin/library/jobs")
async def list_library_jobs(authorization: str = Header(None)):
    """진행 중이거나 실패한 등록 작업. 성공한 작업은 행을 지우므로 여기 없다."""
    require_admin_user(authorization)
    supabase = _supabase_or_503()
    try:
        # source_text는 작품 한 편 분량이라 목록 응답에 싣지 않는다.
        rows = supabase.table("library_jobs") \
            .select("id, title, status, error, created_at") \
            .order("created_at", desc=True).limit(50).execute().data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"등록 작업을 불러오지 못했습니다: {e}")
    for row in rows:
        row["progress"] = _job_progress.get(row["id"])
    return {"jobs": rows}


@router.post("/api/admin/library/jobs/{job_id}/retry")
async def retry_library_job(job_id: str, background_tasks: BackgroundTasks, authorization: str = Header(None)):
    """실패한 작업을 원문에서 다시 시작한다. 배포 중 재시작 등으로
    'processing'에 멈춰 버린 작업도 여기서 되살릴 수 있도록 상태를 가리지
    않는다 — 원문이 남아 있는 한 다시 만드는 건 언제나 안전하다."""
    require_admin_user(authorization)
    supabase = _supabase_or_503()
    try:
        response = supabase.table("library_jobs").select("id").eq("id", job_id).maybe_single().execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"작업을 확인하지 못했습니다: {e}")
    if not response or not response.data:
        raise HTTPException(status_code=404, detail="등록 작업을 찾을 수 없습니다.")

    supabase.table("library_jobs").update({"status": "queued", "error": None}).eq("id", job_id).execute()
    background_tasks.add_task(_process_library_batch, [job_id])
    return {"status": "queued"}


@router.delete("/api/admin/library/jobs/{job_id}")
async def delete_library_job(job_id: str, authorization: str = Header(None)):
    """다시 시도하지 않을 실패 작업을 목록에서 치운다."""
    require_admin_user(authorization)
    supabase = _supabase_or_503()
    try:
        supabase.table("library_jobs").delete().eq("id", job_id).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"작업을 삭제하지 못했습니다: {e}")
    return {"deleted": job_id}


@router.get("/api/admin/library")
async def list_all_library_items(authorization: str = Header(None)):
    """상태(review/published) 상관없이 전체 작품을 관리자에게 보여준다 —
    /api/library(공개 목록)와 달리 published 필터를 걸지 않는다."""
    require_admin_user(authorization)
    supabase = _supabase_or_503()
    try:
        rows = supabase.table("audiobooks") \
            .select("id, title, library_status, library_category, library_description, created_at") \
            .eq("is_library", True).order("created_at", desc=True).execute().data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"작품 목록을 불러오지 못했습니다: {e}")
    return {"items": rows}


@router.patch("/api/admin/library/{audiobook_id}")
async def update_library_status(audiobook_id: str, payload: dict, authorization: str = Header(None)):
    """관리자가 판본/권리를 직접 확인한 뒤에만 published로 전환한다 —
    AI가 대신 "확인됨"이라고 표시하지 않는다는 원칙은 여기서도 유지된다."""
    require_admin_user(authorization)
    status = payload.get("status")
    if status not in LIBRARY_STATUSES:
        raise HTTPException(status_code=400, detail="status는 review 또는 published여야 합니다.")

    supabase = _supabase_or_503()
    try:
        supabase.table("audiobooks").update({"library_status": status}) \
            .eq("id", audiobook_id).eq("is_library", True).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"상태를 변경하지 못했습니다: {e}")
    return {"status": status}


@router.get("/api/library")
async def list_library():
    """공개된(published) 라이브러리 작품 목록. 로그인 여부와 무관하게 볼 수 있다."""
    supabase = _supabase_or_503()
    try:
        rows = supabase.table("audiobooks").select("*") \
            .eq("is_library", True).eq("library_status", "published") \
            .order("created_at", desc=True).execute().data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"라이브러리를 불러오지 못했습니다: {e}")

    items = []
    for row in rows:
        try:
            items.extend(audiobook_items_with_urls(supabase, row["user_id"], [row]))
        except Exception:
            continue
    return {"library": items}


# ⚠️ 이 라우트는 반드시 "/api/library/{audiobook_id}"보다 먼저 등록해야 한다.
# FastAPI는 등록 순서대로 매칭하므로, 뒤에 두면 "saves"가 audiobook_id로
# 잡혀 UUID 캐스팅에서 터진다(실제로 그래서 이 엔드포인트는 추가된 이후
# 한 번도 동작한 적이 없었다).
@router.get("/api/library/saves")
async def list_library_saves(authorization: str = Header(None)):
    """내가 서재에 추가한 라이브러리 작품 목록."""
    user_id = require_user_id(authorization)
    supabase = _supabase_or_503()
    try:
        saves = supabase.table("library_saves").select("audiobook_id") \
            .eq("user_id", user_id).execute().data or []
        audiobook_ids = [s["audiobook_id"] for s in saves]
        if not audiobook_ids:
            return {"library": []}
        rows = supabase.table("audiobooks").select("*") \
            .in_("id", audiobook_ids).execute().data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"내 서재를 불러오지 못했습니다: {e}")

    items = []
    for row in rows:
        try:
            items.extend(audiobook_items_with_urls(supabase, row["user_id"], [row]))
        except Exception:
            continue
    return {"library": items}


@router.get("/api/library/{audiobook_id}")
async def get_library_item(audiobook_id: str):
    """작품 상세. published 상태인 작품만 조회할 수 있다."""
    supabase = _supabase_or_503()
    try:
        response = supabase.table("audiobooks").select("*") \
            .eq("id", audiobook_id).eq("is_library", True).eq("library_status", "published") \
            .maybe_single().execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"작품을 불러오지 못했습니다: {e}")
    if not response or not response.data:
        raise HTTPException(status_code=404, detail="작품을 찾을 수 없습니다.")

    items = audiobook_items_with_urls(supabase, response.data["user_id"], [response.data])
    if not items:
        raise HTTPException(status_code=404, detail="작품 오디오를 찾을 수 없습니다.")
    return items[0]


@router.post("/api/library/{audiobook_id}/save")
async def save_library_item(audiobook_id: str, authorization: str = Header(None)):
    user_id = require_user_id(authorization)
    supabase = _supabase_or_503()
    found = supabase.table("audiobooks").select("id") \
        .eq("id", audiobook_id).eq("is_library", True).eq("library_status", "published").execute().data
    if not found:
        raise HTTPException(status_code=404, detail="작품을 찾을 수 없습니다.")
    try:
        supabase.table("library_saves").upsert(
            {"user_id": user_id, "audiobook_id": audiobook_id}, on_conflict="user_id,audiobook_id"
        ).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"내 서재 추가에 실패했습니다: {e}")
    return {"saved": True}


@router.delete("/api/library/{audiobook_id}/save")
async def unsave_library_item(audiobook_id: str, authorization: str = Header(None)):
    user_id = require_user_id(authorization)
    supabase = _supabase_or_503()
    try:
        supabase.table("library_saves").delete() \
            .eq("user_id", user_id).eq("audiobook_id", audiobook_id).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"내 서재 제거에 실패했습니다: {e}")
    return {"saved": False}
