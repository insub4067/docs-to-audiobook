"""폴더: 오디오북을 정리하기 위한 클라우드 전용 폴더 구조.

오디오북과 달리 폴더는 오프라인 재생이 필요 없어 로컬(IndexedDB)에는
두지 않고, 로그인해서 "내 파일" 탭을 열 때마다 서버에서 그대로 불러온다.
"""
from fastapi import APIRouter, Header, HTTPException

from state import require_user_id, _supabase_or_503
from routes.audiobooks import audiobook_items_with_urls

router = APIRouter()


@router.post("/api/folders")
async def create_folder(payload: dict, authorization: str = Header(None)):
    user_id = require_user_id(authorization)
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="폴더 이름이 필요합니다.")
    parent_folder_id = payload.get("parent_folder_id")

    supabase = _supabase_or_503()
    try:
        if parent_folder_id:
            found = supabase.table("folders").select("id") \
                .eq("id", parent_folder_id).eq("user_id", user_id).execute().data
            if not found:
                raise HTTPException(status_code=404, detail="상위 폴더를 찾을 수 없습니다.")

        response = supabase.table("folders").insert({
            "user_id": user_id,
            "name": name[:255],
            "parent_folder_id": parent_folder_id,
        }).execute()
        return response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"폴더 생성에 실패했습니다: {e}")


@router.get("/api/folders")
async def list_folder_contents(parent_id: str | None = None, authorization: str = Header(None)):
    """parent_id가 없으면 최상위(루트)의 폴더·오디오북을 반환한다."""
    user_id = require_user_id(authorization)
    supabase = _supabase_or_503()

    try:
        current_folder = None
        if parent_id:
            found = supabase.table("folders").select("*") \
                .eq("id", parent_id).eq("user_id", user_id).execute().data
            if not found:
                raise HTTPException(status_code=404, detail="폴더를 찾을 수 없습니다.")
            current_folder = found[0]

        folders_query = supabase.table("folders").select("*").eq("user_id", user_id)
        if parent_id:
            folders_query = folders_query.eq("parent_folder_id", parent_id)
        else:
            folders_query = folders_query.is_("parent_folder_id", "null")
        folders = folders_query.order("name").execute().data or []

        audiobooks_query = supabase.table("audiobooks").select("*").eq("user_id", user_id)
        if parent_id:
            audiobooks_query = audiobooks_query.eq("folder_id", parent_id)
        else:
            audiobooks_query = audiobooks_query.is_("folder_id", "null")
        audiobook_rows = audiobooks_query.order("created_at", desc=True).execute().data or []

        return {
            "current_folder": current_folder,
            "folders": folders,
            "audiobooks": audiobook_items_with_urls(supabase, user_id, audiobook_rows),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"폴더 내용을 불러오지 못했습니다: {e}")


@router.patch("/api/folders/{folder_id}")
async def update_folder(folder_id: str, payload: dict, authorization: str = Header(None)):
    """폴더 이름 변경 및/또는 다른 폴더로 이동."""
    user_id = require_user_id(authorization)
    supabase = _supabase_or_503()

    updates = {}
    if "name" in payload:
        name = (payload.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="폴더 이름이 필요합니다.")
        updates["name"] = name[:255]
    if "parent_folder_id" in payload:
        new_parent = payload.get("parent_folder_id")
        if new_parent == folder_id:
            raise HTTPException(status_code=400, detail="폴더를 자기 자신 안으로 옮길 수 없습니다.")
        if new_parent:
            found = supabase.table("folders").select("id") \
                .eq("id", new_parent).eq("user_id", user_id).execute().data
            if not found:
                raise HTTPException(status_code=404, detail="상위 폴더를 찾을 수 없습니다.")
        updates["parent_folder_id"] = new_parent

    if not updates:
        raise HTTPException(status_code=400, detail="수정할 내용이 없습니다.")

    try:
        response = supabase.table("folders").update(updates) \
            .eq("id", folder_id).eq("user_id", user_id).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="폴더를 찾을 수 없습니다.")
        return response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"폴더 수정에 실패했습니다: {e}")


@router.delete("/api/folders/{folder_id}")
async def delete_folder(folder_id: str, authorization: str = Header(None)):
    """폴더를 지우면 안의 파일·하위 폴더는 삭제되지 않고 상위(또는 루트)로 옮겨진다."""
    user_id = require_user_id(authorization)
    supabase = _supabase_or_503()

    try:
        found = supabase.table("folders").select("*") \
            .eq("id", folder_id).eq("user_id", user_id).execute().data
        if not found:
            raise HTTPException(status_code=404, detail="폴더를 찾을 수 없습니다.")
        parent_folder_id = found[0]["parent_folder_id"]

        supabase.table("folders").update({"parent_folder_id": parent_folder_id}) \
            .eq("parent_folder_id", folder_id).eq("user_id", user_id).execute()
        supabase.table("audiobooks").update({"folder_id": parent_folder_id}) \
            .eq("folder_id", folder_id).eq("user_id", user_id).execute()

        supabase.table("folders").delete() \
            .eq("id", folder_id).eq("user_id", user_id).execute()
        return {"deleted": folder_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"폴더 삭제에 실패했습니다: {e}")
