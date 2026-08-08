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
    # 같은 붙여넣기 안에 같은 기사가 두 번 들어오는 일이 있다(GPT가 같은
    # 뉴스를 다른 출처로 두 번 뽑는 경우). 제목을 공백·대소문자만 정규화해
    # 비교하고 먼저 온 것만 남긴다.
    seen_titles = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or "").strip()
        content = _strip_citation_artifacts((item.get("content") or "").strip())
        if not title or not content:
            continue
        title_key = re.sub(r"\s+", " ", title).casefold()
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)
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


def _all_news_rows(supabase) -> list[dict]:
    return supabase.table("audiobooks").select("id, user_id") \
        .eq("is_news", True).execute().data or []


def _delete_news_rows(supabase, rows: list[dict]) -> int:
    """행과 Storage 음성 파일을 함께 지운다. 행만 지우면 화면에서는 사라져도
    버킷은 계속 불어난다."""
    for row in rows:
        audio_path, sentences_path = _object_paths(row["user_id"], row["id"])
        try:
            supabase.storage.from_(AUDIOBOOK_BUCKET).remove([audio_path, sentences_path])
        except Exception:
            # 파일이 이미 없어도 행은 정리해야 한다
            logger.exception("뉴스 정리 중 스토리지 삭제 실패 id=%s", row["id"])
        supabase.table("audiobooks").delete().eq("id", row["id"]).execute()
    return len(rows)


def _enforce_news_limit(supabase) -> int:
    """DB에 뉴스는 항상 최신 NEWS_LIST_LIMIT개까지만 남긴다.

    새 묶음이 이전 것을 통째로 대체하므로 보통은 지울 게 없지만, 대체가
    부분적으로 실패했거나 예전 데이터가 남아 있을 때를 위한 마지막 방어선이다.

    남길 집합은 파이썬이 아니라 DB에 물어서 정한다 — 날짜 문자열을 직접
    비교하면 형식 차이로 어긋날 수 있다."""
    keep_rows = supabase.table("audiobooks").select("id") \
        .eq("is_news", True).order("created_at", desc=True) \
        .limit(NEWS_LIST_LIMIT).execute().data or []
    keep_ids = {row["id"] for row in keep_rows}

    extra = [row for row in _all_news_rows(supabase) if row["id"] not in keep_ids]
    return _delete_news_rows(supabase, extra)


async def _process_news_batch(job_ids: list[str], previous_rows: list[dict]) -> None:
    """항목마다 TTS 합성이 걸려 전체가 수십 초~수 분 걸릴 수 있다.
    관리자가 응답을 기다리지 않도록 백그라운드로 돌리고, 다 끝나면
    구독한 모든 사용자에게 새 뉴스가 왔다고 한 번만 알린다."""
    created = await run_jobs(job_ids)

    if created:
        # ⚠️ 이전 뉴스는 새 묶음이 하나라도 만들어진 뒤에 지운다. 등록을
        # 받자마자 지우면 합성이 통째로 실패했을 때 화면에 아무것도 남지
        # 않는다 — 새 뉴스가 없는 것보다 어제 뉴스라도 있는 게 낫다.
        try:
            _delete_news_rows(_supabase_or_503(), previous_rows)
        except Exception:
            logger.exception("이전 뉴스 삭제 실패")

        try:
            send_news_ready_broadcast(len(created))
        except Exception:
            logger.exception("경제 뉴스 등록 완료 알림 발송 실패")

    try:
        _enforce_news_limit(_supabase_or_503())
    except Exception:
        logger.exception("뉴스 개수 정리 실패")


@router.post("/api/admin/news")
async def add_news(payload: dict, background_tasks: BackgroundTasks, authorization: str = Header(None)):
    admin_user_id = require_admin_user(authorization)
    items = _parse_news_payload(payload.get("text") or "")[:NEWS_LIST_LIMIT]
    supabase = _supabase_or_503()

    # ⚠️ 이미 처리 중인 묶음이 있으면 받지 않는다. 실수로 두 번 눌러 두
    # 묶음이 겹치면, 두 번째가 캡처한 "이전 목록"에 첫 번째 결과가 아직
    # 없어서 그것만 살아남는다. 실제로 그렇게 같은 기사가 두 번씩 든
    # 목록이 만들어졌다.
    in_flight = supabase.table("content_jobs").select("id") \
        .eq("kind", "news").in_("status", ["queued", "processing"]) \
        .limit(1).execute().data or []
    if in_flight:
        raise HTTPException(
            status_code=429,
            detail="이미 처리 중인 뉴스 등록이 있습니다. 완료 후 다시 시도해 주세요.",
        )

    # 새 묶음이 성공하면 이 목록을 통째로 지운다(_process_news_batch).
    previous_rows = _all_news_rows(supabase)

    job_ids = queue_jobs(supabase, "news", admin_user_id, items)
    background_tasks.add_task(_process_news_batch, job_ids, previous_rows)
    return {"queued": len(job_ids), "replacing": len(previous_rows)}


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
