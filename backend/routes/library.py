"""라이브러리: 공개 이용 가능한 경전·철학서·고전문학을 관리자가 등록해
개인 문서/경제 뉴스와 같은 파이프라인(TTS 합성 → Storage 저장)으로
오디오북화한다. 완성된 작품은 별도 테이블 없이 audiobooks를 재사용하고
is_library로 구분한다. 합성이 끝나기 전까지의 등록 작업은 뉴스와 공용인
content_jobs에 남긴다(routes/content_jobs.py 참고) — 원문을 들고 있어야
실패한 작품을 다시 만들 수 있기 때문이다.

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
from routes.content_jobs import queue_jobs, run_jobs, progress_callback_for
from routes.tts import synthesize_document
from tts_providers.voice_catalog import DEFAULT_VOICE_KEY

router = APIRouter()
logger = logging.getLogger(__name__)

LIBRARY_STATUSES = {"review", "published"}


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


async def store_library_item(supabase, admin_user_id: str, item: dict, job_id: str) -> str:
    """content_jobs 처리기가 호출하는 저장 함수(kind='library')."""
    status = item.get("status") if item.get("status") in LIBRARY_STATUSES else "review"
    audio_bytes, sentences, _headings = await synthesize_document(
        item["content"], DEFAULT_VOICE_KEY, "+5%", "+0Hz", progress_callback=progress_callback_for(job_id)
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
        "library_status": status,
        "library_category": item.get("category"),
        "library_edition": item.get("edition"),
        "library_translator": item.get("translator"),
        "library_source": item.get("source"),
        "library_rights": item.get("rights"),
        "library_description": item.get("description"),
        "library_chapter_count": chapter_count,
    }).execute()
    return audiobook_id


@router.post("/api/admin/library")
async def add_library_items(payload: dict, background_tasks: BackgroundTasks, authorization: str = Header(None)):
    admin_user_id = require_admin_user(authorization)
    items = _parse_library_payload(payload.get("text") or "")

    job_ids = queue_jobs(_supabase_or_503(), "library", admin_user_id, items)
    background_tasks.add_task(run_jobs, job_ids)
    return {"queued": len(job_ids)}


@router.get("/api/admin/library")
async def list_all_library_items(authorization: str = Header(None)):
    """상태(review/published) 상관없이 전체 작품을 관리자에게 보여준다 —
    /api/library(공개 목록)와 달리 published 필터를 걸지 않는다."""
    require_admin_user(authorization)
    supabase = _supabase_or_503()
    try:
        rows = supabase.table("audiobooks") \
            .select("id, title, library_status, library_category, library_edition, "
                    "library_translator, library_source, library_rights, library_description, created_at") \
            .eq("is_library", True).order("created_at", desc=True).execute().data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"작품 목록을 불러오지 못했습니다: {e}")
    return {"items": rows}


# 편집 가능한 서지 정보. 본문(오디오)은 여기서 못 바꾼다 — 텍스트를 고치면
# 음성을 다시 합성해야 하므로 재등록 경로를 써야 한다.
EDITABLE_LIBRARY_FIELDS = {
    "title": ("title", 255),
    "category": ("library_category", 50),
    "edition": ("library_edition", 255),
    "translator": ("library_translator", 255),
    "source": ("library_source", 255),
    "rights": ("library_rights", None),
    "description": ("library_description", None),
}


@router.patch("/api/admin/library/{audiobook_id}")
async def update_library_item(audiobook_id: str, payload: dict, authorization: str = Header(None)):
    """공개 상태와 서지 정보를 고친다.

    관리자가 판본/권리를 직접 확인한 뒤에만 published로 전환한다 —
    AI가 대신 "확인됨"이라고 표시하지 않는다는 원칙은 여기서도 유지된다.

    제목 오타 하나 때문에 작품을 지우고 다시 등록(수 분짜리 재합성)하게
    두지 않으려고 서지 정보 수정을 함께 받는다. payload에 들어 있는 키만
    고치므로, status만 보내던 기존 호출은 그대로 동작한다.
    """
    require_admin_user(authorization)

    changes: dict = {}
    if "status" in payload:
        status = payload.get("status")
        if status not in LIBRARY_STATUSES:
            raise HTTPException(status_code=400, detail="status는 review 또는 published여야 합니다.")
        changes["library_status"] = status

    for key, (column, max_length) in EDITABLE_LIBRARY_FIELDS.items():
        if key not in payload:
            continue
        value = (payload.get(key) or "").strip()
        if max_length:
            value = value[:max_length]
        # 제목이 비면 목록에서 어느 작품인지 알 수 없게 된다.
        if key == "title" and not value:
            raise HTTPException(status_code=400, detail="제목은 비울 수 없습니다.")
        changes[column] = value or None

    if not changes:
        raise HTTPException(status_code=400, detail="변경할 내용이 없습니다.")

    supabase = _supabase_or_503()
    try:
        supabase.table("audiobooks").update(changes) \
            .eq("id", audiobook_id).eq("is_library", True).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"작품을 수정하지 못했습니다: {e}")
    return {"updated": changes}


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


# ⚠️ 이 라우트도 "/api/library/{audiobook_id}"보다 먼저 등록해야 한다(saves와 같은 이유).
@router.get("/api/library/playback")
async def list_library_playback(authorization: str = Header(None)):
    """내 재생 위치를 audiobook_id로 묶어 한 번에 돌려준다.

    목록 카드마다 /api/audiobooks/{id}/playback을 부르면 작품 수만큼
    요청이 나간다(N+1). 목록은 스크롤하면서 보는 화면이라 그만큼 느려진다.
    """
    user_id = require_user_id(authorization)
    supabase = _supabase_or_503()
    try:
        rows = supabase.table("playback_history") \
            .select("audiobook_id, current_time_seconds") \
            .eq("user_id", user_id).execute().data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"재생 위치를 불러오지 못했습니다: {e}")
    return {"positions": {row["audiobook_id"]: row.get("current_time_seconds") or 0 for row in rows}}


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
