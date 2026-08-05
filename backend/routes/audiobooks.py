"""클라우드 보관함: 오디오북 CRUD 및 재생 상태.

IndexedDB가 재생 원본이고 여기는 백업 및 기기 간 전달 통로다.
오디오북은 만든 뒤 편집이 없어 생성/삭제만 있으므로 충돌 병합이 필요 없다.
파일 본체는 클라이언트가 서명 URL로 Supabase와 직접 주고받는다 —
서버를 거치면 최대 90MB가 매번 인스턴스 메모리를 지나간다.
"""
import logging
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Request, Header, HTTPException
from postgrest.exceptions import APIError

from state import (
    AUDIOBOOK_BUCKET, SIGNED_URL_TTL, require_user_id, _supabase_or_503,
    _object_paths, enforce_rate_limit, _validate_folder_ownership,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def audiobook_items_with_urls(supabase, user_id: str, rows: list) -> list:
    """오디오북 행마다 재생/문장 데이터용 서명 URL을 붙인다.
    /api/audiobooks와 /api/folders(폴더 내용 조회)가 같이 쓴다."""
    storage = supabase.storage.from_(AUDIOBOOK_BUCKET)
    items = []
    for row in rows:
        audio_path, sentences_path = _object_paths(user_id, row["id"])
        item = dict(row)
        # 오디오가 없으면 재생이 불가능하므로 그 항목만 목록에서 제외한다
        # (업로드가 중간에 끊긴 행). 목록 전체를 실패시키지는 않는다.
        try:
            item["audio_url"] = storage.create_signed_url(audio_path, SIGNED_URL_TTL)["signedURL"]
        except Exception:
            continue
        # 문장 데이터는 없어도 오디오 재생은 되므로 선택 사항으로 둔다
        try:
            item["sentences_url"] = storage.create_signed_url(sentences_path, SIGNED_URL_TTL)["signedURL"]
        except Exception:
            item["sentences_url"] = None
        items.append(item)
    return items


@router.post("/api/audiobooks")
async def create_audiobook(request: Request, payload: dict, authorization: str = Header(None)):
    """메타데이터 행을 만들고 업로드용 서명 URL을 돌려준다."""
    user_id = require_user_id(authorization)
    enforce_rate_limit(request, "audiobook_create", limit=60, window_sec=600)

    title = (payload.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="제목이 필요합니다.")

    supabase = _supabase_or_503()

    folder_id = payload.get("folder_id")
    if folder_id:
        _validate_folder_ownership(supabase, user_id, folder_id)

    audiobook_id = str(uuid.uuid4())
    audio_path, sentences_path = _object_paths(user_id, audiobook_id)

    try:
        supabase.table("audiobooks").insert({
            "id": audiobook_id,
            "user_id": user_id,
            "title": title[:255],
            "file_name": (payload.get("file_name") or title)[:255],
            "duration_seconds": payload.get("duration_seconds"),
            "storage_path": audio_path,
            "folder_id": folder_id,
        }).execute()

        storage = supabase.storage.from_(AUDIOBOOK_BUCKET)
        return {
            "id": audiobook_id,
            "audio_upload": storage.create_signed_upload_url(audio_path),
            "sentences_upload": storage.create_signed_upload_url(sentences_path),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"클라우드 등록에 실패했습니다: {e}")


@router.get("/api/audiobooks")
async def list_audiobooks(authorization: str = Header(None)):
    """내 오디오북 목록. 각 항목에 다운로드용 서명 URL을 붙인다."""
    user_id = require_user_id(authorization)
    supabase = _supabase_or_503()

    try:
        # is_news/is_library 항목은 관리자 계정에 심어둔 공용 콘텐츠라
        # 개인 보관함에는 섞이면 안 된다.
        rows = supabase.table("audiobooks").select("*").eq("user_id", user_id) \
            .eq("is_news", False).eq("is_library", False) \
            .order("created_at", desc=True).execute().data or []
        return {"audiobooks": audiobook_items_with_urls(supabase, user_id, rows)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"목록을 불러오지 못했습니다: {e}")


@router.patch("/api/audiobooks/{audiobook_id}")
async def update_audiobook(audiobook_id: str, payload: dict, authorization: str = Header(None)):
    """내 오디오북 제목·소속 폴더·북마크 여부를 수정한다."""
    user_id = require_user_id(authorization)
    supabase = _supabase_or_503()

    updates = {}
    if "title" in payload:
        title = (payload.get("title") or "").strip()
        if not title:
            raise HTTPException(status_code=400, detail="제목이 필요합니다.")
        updates["title"] = title[:255]
    if "folder_id" in payload:
        folder_id = payload.get("folder_id")
        if folder_id:
            _validate_folder_ownership(supabase, user_id, folder_id)
        updates["folder_id"] = folder_id
    if "is_bookmarked" in payload:
        updates["is_bookmarked"] = bool(payload.get("is_bookmarked"))

    if not updates:
        raise HTTPException(status_code=400, detail="수정할 내용이 없습니다.")

    try:
        response = supabase.table("audiobooks").update(updates) \
            .eq("id", audiobook_id).eq("user_id", user_id).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="해당 오디오북을 찾을 수 없습니다.")
        return response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"수정에 실패했습니다: {e}")


def _validate_playback_state(payload: dict) -> tuple[float, float, str]:
    position = payload.get("current_time_seconds")
    speed = payload.get("playback_speed", 1.0)
    repeat_mode = payload.get("repeat_mode", "off")
    if not isinstance(position, (int, float)) or isinstance(position, bool) or position < 0:
        raise HTTPException(status_code=400, detail="재생 위치가 올바르지 않습니다.")
    if speed not in (0.75, 1.0, 1.25, 1.5, 2.0):
        raise HTTPException(status_code=400, detail="재생 속도가 올바르지 않습니다.")
    if repeat_mode not in ("off", "all", "one"):
        raise HTTPException(status_code=400, detail="반복 모드가 올바르지 않습니다.")
    return position, speed, repeat_mode


@router.get("/api/audiobooks/{audiobook_id}/playback")
async def get_playback_state(audiobook_id: str, authorization: str = Header(None)):
    """현재 계정의 오디오북 재생 상태를 반환한다."""
    user_id = require_user_id(authorization)
    supabase = _supabase_or_503()
    try:
        response = supabase.table("playback_history").select("*") \
            .eq("audiobook_id", audiobook_id).eq("user_id", user_id).maybe_single().execute()
        # postgrest-py는 일치하는 행이 0개면 .execute()가 None을 돌려준다
        # (버전에 따른 동작). response.data로 바로 접근하면 AttributeError.
        if response and response.data:
            return response.data
        return {
            "audiobook_id": audiobook_id,
            "current_time_seconds": 0,
            "playback_speed": 1.0,
            "repeat_mode": "off",
        }
    except Exception as e:
        logger.exception("재생 상태 조회 실패 audiobook_id=%s", audiobook_id)
        raise HTTPException(status_code=500, detail=f"재생 상태를 불러오지 못했습니다: {e}")


@router.put("/api/audiobooks/{audiobook_id}/playback")
async def save_playback_state(audiobook_id: str, payload: dict, authorization: str = Header(None)):
    """현재 계정의 오디오북 재생 상태를 최신 값으로 저장한다."""
    user_id = require_user_id(authorization)
    position, speed, repeat_mode = _validate_playback_state(payload)
    supabase = _supabase_or_503()
    state = {
        "user_id": user_id,
        "audiobook_id": audiobook_id,
        "current_time_seconds": position,
        "playback_speed": speed,
        "repeat_mode": repeat_mode,
        "last_played_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        response = supabase.table("playback_history").upsert(
            state, on_conflict="user_id,audiobook_id"
        ).execute()
        return response.data[0] if response.data else state
    except APIError as e:
        # 23503 = foreign_key_violation. 다른 기기에서 이미 삭제된 오디오북을
        # 아직 동기화 전인 기기가 재생 중일 때 발생한다 — 클라이언트는 이
        # 실패를 조용히 무시하므로(재생 자체는 계속) 500 대신 404로 명확히
        # 구분해 로그에 진짜 서버 오류처럼 쌓이지 않게 한다.
        if e.code == "23503":
            logger.warning("존재하지 않는 오디오북의 재생 상태 저장 시도 audiobook_id=%s", audiobook_id)
            raise HTTPException(status_code=404, detail="삭제되었거나 존재하지 않는 오디오북입니다.")
        logger.exception("재생 상태 저장 실패 audiobook_id=%s", audiobook_id)
        raise HTTPException(status_code=500, detail=f"재생 상태 저장에 실패했습니다: {e}")
    except Exception as e:
        logger.exception("재생 상태 저장 실패 audiobook_id=%s", audiobook_id)
        raise HTTPException(status_code=500, detail=f"재생 상태 저장에 실패했습니다: {e}")


@router.delete("/api/audiobooks/{audiobook_id}")
async def delete_audiobook(audiobook_id: str, authorization: str = Header(None)):
    user_id = require_user_id(authorization)
    supabase = _supabase_or_503()

    try:
        # user_id를 조건에 포함해 남의 항목을 지울 수 없게 한다
        found = supabase.table("audiobooks").select("id") \
            .eq("id", audiobook_id).eq("user_id", user_id).execute().data
        if not found:
            raise HTTPException(status_code=404, detail="해당 오디오북을 찾을 수 없습니다.")

        audio_path, sentences_path = _object_paths(user_id, audiobook_id)
        try:
            supabase.storage.from_(AUDIOBOOK_BUCKET).remove([audio_path, sentences_path])
        except Exception:
            # 파일이 이미 없어도 행은 정리해야 한다
            pass

        supabase.table("audiobooks").delete() \
            .eq("id", audiobook_id).eq("user_id", user_id).execute()
        return {"deleted": audiobook_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"삭제에 실패했습니다: {e}")
