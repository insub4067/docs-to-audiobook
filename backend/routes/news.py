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
from routes.content_jobs import queue_jobs, run_jobs, progress_callback_for
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


async def store_news_item(supabase, admin_user_id: str, item: dict, job_id: str) -> str:
    """content_jobs 처리기가 호출하는 저장 함수(kind='news')."""
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

    # 목록 헤더에 "총 N개 · 약 M분"을 보여주려고 미리 계산해 둔다 — library.py와
    # 동일한 패턴 (매번 sentences 파일을 내려받으면 목록 화면이 느려진다).
    duration_seconds = round(max((s.get("end", 0) for s in sentences), default=0) / 1000)

    supabase.table("audiobooks").insert({
        "id": audiobook_id,
        "user_id": admin_user_id,
        "title": item["title"],
        "file_name": item["title"],
        "storage_path": audio_path,
        "duration_seconds": duration_seconds,
        "is_news": True,
        "news_category": item.get("category"),
        "news_source": item.get("source"),
    }).execute()
    return audiobook_id


def _cleanup_stale_news(supabase) -> int:
    """list_news 공개 목록에서 이미 벗어난(3일 초과 또는 최신 10개 밖으로
    밀려난) 뉴스 오디오북을 실제로 지운다. 안 지우면 화면엔 안 보여도
    DB 행과 Storage 음성 파일이 계속 쌓인다.

    "보이는" 집합은 list_news와 정확히 같은 조건(같은 gte+order+limit
    쿼리)으로 DB에 직접 물어서 구한다 — 날짜 문자열을 파이썬에서 직접
    비교하면 형식 차이로 어긋날 수 있어서다."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=NEWS_VISIBLE_DAYS)).isoformat()
    visible_rows = supabase.table("audiobooks").select("id") \
        .eq("is_news", True).gte("created_at", cutoff) \
        .order("created_at", desc=True).limit(NEWS_LIST_LIMIT).execute().data or []
    visible_ids = {row["id"] for row in visible_rows}

    all_rows = supabase.table("audiobooks").select("id, user_id") \
        .eq("is_news", True).execute().data or []
    stale_rows = [row for row in all_rows if row["id"] not in visible_ids]

    for row in stale_rows:
        audio_path, sentences_path = _object_paths(row["user_id"], row["id"])
        try:
            supabase.storage.from_(AUDIOBOOK_BUCKET).remove([audio_path, sentences_path])
        except Exception:
            # 파일이 이미 없어도 행은 정리해야 한다
            logger.exception("뉴스 정리 중 스토리지 삭제 실패 id=%s", row["id"])
        supabase.table("audiobooks").delete().eq("id", row["id"]).execute()

    return len(stale_rows)


async def _process_news_batch(job_ids: list[str]) -> None:
    """항목마다 TTS 합성이 걸려 전체가 수십 초~수 분 걸릴 수 있다.
    관리자가 응답을 기다리지 않도록 백그라운드로 돌리고, 다 끝나면
    구독한 모든 사용자에게 새 뉴스가 왔다고 한 번만 알린다."""
    created = await run_jobs(job_ids)

    if created:
        try:
            send_news_ready_broadcast(len(created))
        except Exception:
            logger.exception("경제 뉴스 등록 완료 알림 발송 실패")

    try:
        _cleanup_stale_news(_supabase_or_503())
    except Exception:
        logger.exception("오래된 뉴스 정리 실패")


@router.post("/api/admin/news")
async def add_news(payload: dict, background_tasks: BackgroundTasks, authorization: str = Header(None)):
    admin_user_id = require_admin_user(authorization)
    items = _parse_news_payload(payload.get("text") or "")[:NEWS_LIST_LIMIT]

    job_ids = queue_jobs(_supabase_or_503(), "news", admin_user_id, items)
    background_tasks.add_task(_process_news_batch, job_ids)
    return {"queued": len(job_ids)}


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
