"""경제 뉴스: 관리자가 붙여넣은 JSON 뉴스 목록을 오디오북으로 변환해 저장.

뉴스 항목도 결국 "제목 + 본문 + 음성"이라 별도 테이블 없이 기존
audiobooks 테이블·Storage 버킷을 그대로 쓰고 is_news 플래그로만 구분한다.
개인 오디오북과 달리 소유자와 무관하게 모든 사용자에게 노출되는 공개
목록이라, 조회 API는 로그인 여부를 따지지 않는다.
"""
import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException

from state import _supabase_or_503, require_admin_user, AUDIOBOOK_BUCKET, _object_paths
from routes.audiobooks import audiobook_items_with_urls
from routes.tts import synthesize_document
from tts_providers.voice_catalog import DEFAULT_VOICE_KEY
from push_notifications import send_news_ready_broadcast

router = APIRouter()
logger = logging.getLogger(__name__)

# 오래된 뉴스가 계속 남아있지 않도록 생성일 기준으로만 걸러낸다. 실제
# "게시 시각" 파싱은 신뢰하기 어려워(GPT가 자유 형식으로 줌) 아예 안 쓴다.
NEWS_VISIBLE_DAYS = 3
NEWS_LIST_LIMIT = 10

# ChatGPT가 웹검색 결과를 인용할 때 본문에 [oaicitation:8‡Reuters] 같은
# 마커를 그대로 남겨두는 경우가 있다 — 걸러내지 않으면 이게 TTS로 그대로
# 읽히고 화면에도 깨진 문장처럼 보인다.
_CITATION_ARTIFACT_RE = re.compile(r"\[oaicitation:[^\]]*\]", re.IGNORECASE)


def _strip_citation_artifacts(text: str) -> str:
    cleaned = _CITATION_ARTIFACT_RE.sub("", text)
    cleaned = re.sub(r"\s+([.,!?])", r"\1", cleaned)
    cleaned = re.sub(r"([.!?]){2,}", r"\1", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip()


def _parse_news_payload(raw_text: str) -> list[dict]:
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
        raise HTTPException(status_code=400, detail="뉴스 배열이 비어 있습니다.")

    parsed = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or "").strip()
        content = _strip_citation_artifacts((item.get("content") or "").strip())
        if not title or not content:
            continue
        parsed.append({
            "title": title[:255],
            "content": content,
            "category": (item.get("category") or "").strip()[:50] or None,
            "source": (item.get("source") or "").strip()[:100] or None,
        })

    if not parsed:
        raise HTTPException(status_code=400, detail="title/content가 있는 뉴스 항목이 없습니다.")
    return parsed


async def _store_news_item(supabase, admin_user_id: str, item: dict) -> str:
    audio_bytes, sentences, _headings = await synthesize_document(
        item["content"], DEFAULT_VOICE_KEY, "+5%", "+0Hz"
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

    supabase.table("audiobooks").insert({
        "id": audiobook_id,
        "user_id": admin_user_id,
        "title": item["title"],
        "file_name": item["title"],
        "storage_path": audio_path,
        "is_news": True,
        "news_category": item["category"],
        "news_source": item["source"],
    }).execute()
    return audiobook_id


async def _process_news_batch(admin_user_id: str, items: list[dict]) -> None:
    """항목마다 TTS 합성이 걸려 전체가 수십 초~수 분 걸릴 수 있다.
    관리자가 응답을 기다리지 않도록 백그라운드로 돌리고, 다 끝나면
    구독한 모든 사용자에게 새 뉴스가 왔다고 한 번만 알린다."""
    supabase = _supabase_or_503()
    created = []
    for item in items:
        try:
            audiobook_id = await _store_news_item(supabase, admin_user_id, item)
            created.append({"id": audiobook_id, "title": item["title"]})
        except Exception:
            logger.exception("뉴스 항목 등록 실패 title=%s", item["title"])

    if created:
        try:
            send_news_ready_broadcast(len(created))
        except Exception:
            logger.exception("경제 뉴스 등록 완료 알림 발송 실패")


@router.post("/api/admin/news")
async def add_news(payload: dict, background_tasks: BackgroundTasks, authorization: str = Header(None)):
    admin_user_id = require_admin_user(authorization)
    items = _parse_news_payload(payload.get("text") or "")[:NEWS_LIST_LIMIT]

    background_tasks.add_task(_process_news_batch, admin_user_id, items)
    return {"queued": len(items)}


@router.get("/api/news")
async def list_news():
    """경제 뉴스 공개 목록. 로그인 여부와 무관하게 누구나 볼 수 있다."""
    supabase = _supabase_or_503()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=NEWS_VISIBLE_DAYS)).isoformat()
    try:
        rows = supabase.table("audiobooks").select("*") \
            .eq("is_news", True).gte("created_at", cutoff) \
            .order("created_at", desc=True).limit(NEWS_LIST_LIMIT).execute().data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"뉴스를 불러오지 못했습니다: {e}")

    items = []
    for row in rows:
        try:
            items.extend(audiobook_items_with_urls(supabase, row["user_id"], [row]))
        except Exception:
            continue
    return {"news": items}
