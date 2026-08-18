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

from state import (
    MAX_ADMIN_SYNTH_CHARS, supabase_or_503, require_admin_user, require_user_id,
    remove_audiobook_objects,
)
from routes.audiobooks import audiobook_items_with_urls
from routes.content_jobs import queue_jobs, run_jobs, synthesize_into_storage

router = APIRouter()
logger = logging.getLogger(__name__)

LIBRARY_STATUSES = {"review", "published"}

# 한 번에 등록할 수 있는 "부"의 수와 부 하나의 본문 길이 상한.
#
# 관리자용이라 악의가 아니라 실수를 막는 장치다. 붙여넣기 한 번에 긴 경전
# 수십 편이 들어오면 합성이 몇 시간 이어지고, 그동안 공유 CPU 하나를 물고
# 있어 일반 사용자 변환까지 굶는다. 상한에 걸리면 나눠서 등록하면 된다.
#
# ⚠️ 세는 단위는 작품이 아니라 부다. 24권짜리 시리즈 하나는 작품 수로는
# 1이지만 합성은 24번 돈다 — CPU를 물고 있는 시간을 재는 게 목적이므로
# 부를 세야 맞다. 전 24권 서사시가 한 번에 들어가도록 30으로 둔다.
#
# 본문 상한은 개인 문서의 관리자 합성 상한과 같은 값으로 맞춘다
# (state.MAX_ADMIN_SYNTH_CHARS) — 같은 엔진으로 같은 일을 하는데 경로에
# 따라 다른 한계를 두면 설명할 수 없다.
MAX_LIBRARY_PARTS_PER_REQUEST = 30


def _check_content_length(title: str, content: str) -> None:
    if len(content) > MAX_ADMIN_SYNTH_CHARS:
        raise HTTPException(
            status_code=413,
            detail=f"'{title[:40]}'의 본문이 너무 깁니다. 최대 {MAX_ADMIN_SYNTH_CHARS:,}자까지 "
                   f"등록할 수 있습니다 (현재 {len(content):,}자).",
        )


def _parse_parts(raw_parts, work_title: str) -> list[dict] | None:
    """parts 배열을 [{title, content}]로 읽는다. parts 키가 없으면 None(단권).

    배열 순서가 그대로 재생 순서다. 번호를 따로 받지 않는 이유는, 받으면
    빠진 번호나 중복 번호를 어떻게 다룰지 정해야 하는데 순서만으로 충분히
    표현되기 때문이다.
    """
    if raw_parts is None:
        return None
    if not isinstance(raw_parts, list) or not raw_parts:
        raise HTTPException(status_code=400, detail=f"'{work_title[:40]}'의 parts가 비어 있습니다.")

    parts = []
    for part in raw_parts:
        if not isinstance(part, dict):
            continue
        content = (part.get("content") or "").strip()
        if not content:
            continue
        _check_content_length(work_title, content)
        parts.append({
            "title": (part.get("title") or "").strip()[:255] or None,
            "content": content,
        })

    if not parts:
        raise HTTPException(status_code=400, detail=f"'{work_title[:40]}'에 content가 있는 부가 없습니다.")
    return parts


def _parse_library_payload(raw_text: str) -> list[dict]:
    """JSON을 작품 목록으로 읽는다. 각 작품은 parts를 하나 이상 갖는다.

    작품은 두 형태로 들어온다.
      - 단권: content에 본문이 통째로 들어 있다(지금까지의 형태).
      - 시리즈: parts에 [{title, content}, ...]가 들어 있다.

    단권도 "부가 하나인 작품"으로 펴서 돌려준다 — 뒤쪽 저장 경로가 갈리지
    않게 하려는 것이다. 서지 정보(판본·역자·권리)는 두 형태가 완전히 같아서
    검증도 한 벌만 유지한다.
    """
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
    # 작품 하나는 최소 한 부라서, 작품 수만으로도 상한 초과를 미리 걸러낸다.
    # 본문 수만 개를 파싱한 뒤에 거절하지 않으려는 것이다.
    if len(items) > MAX_LIBRARY_PARTS_PER_REQUEST:
        raise HTTPException(
            status_code=413,
            detail=f"한 번에 최대 {MAX_LIBRARY_PARTS_PER_REQUEST}개까지 등록할 수 있습니다 "
                   f"(현재 {len(items)}편). 나눠서 등록해 주세요.",
        )

    parsed = []
    total_parts = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or "").strip()
        if not title:
            continue

        parts = _parse_parts(item.get("parts"), title)
        if parts is None:
            content = (item.get("content") or "").strip()
            if not content:
                continue
            _check_content_length(title, content)
            # 단권은 부 제목이 없다. 이 None이 뒤에서 "단권"의 표지가 된다.
            parts = [{"title": None, "content": content}]

        total_parts += len(parts)
        status = item.get("status") if item.get("status") in LIBRARY_STATUSES else "review"
        parsed.append({
            "title": title[:255],
            "parts": parts,
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
    if total_parts > MAX_LIBRARY_PARTS_PER_REQUEST:
        raise HTTPException(
            status_code=413,
            detail=f"한 번에 최대 {MAX_LIBRARY_PARTS_PER_REQUEST}개까지 등록할 수 있습니다 "
                   f"(현재 {total_parts}개). 나눠서 등록해 주세요.",
        )
    return parsed


def _expand_to_job_items(works: list[dict]) -> list[dict]:
    """작품 목록을 content_jobs에 넣을 항목(부 하나 = 항목 하나)으로 편다.

    ⚠️ 오디오북 id를 저장 시점이 아니라 여기서 확정한다. 2부는 자기가 어느
    작품에 속하는지 적어야 하는데, 그 값은 1부의 id다 — 저장할 때 uuid를
    만들면 2부가 미리 알 방법이 없다. 미리 뽑아 두면 세 가지가 따라온다.

      - 부들이 어떤 순서로 합성되든, 중간 몇 개가 실패하든 관계가 어긋나지
        않는다. 순서 의존이 아예 없어진다.
      - 실패한 부를 재시도하면 같은 id로 행이 되살아나, 이미 만들어져 있던
        나머지 부에 그대로 붙는다. 1부가 실패해 작품이 통째로 안 보이던
        상태도 재시도 한 번으로 복구된다.
      - 같은 작업이 어쩌다 두 번 돌면 두 번째가 기본키 충돌로 막힌다.
        무작위 uuid였다면 같은 부의 오디오북이 조용히 두 개 생겼을 자리다.
    """
    job_items = []
    for work in works:
        parts = work["parts"]
        work_title = work["title"]
        metadata = {key: value for key, value in work.items() if key != "parts"}
        work_id = str(uuid.uuid4())
        # 부 제목이 없는 한 부짜리는 시리즈가 아니라 예전 그대로의 단권이다.
        is_single = len(parts) == 1 and parts[0]["title"] is None

        for index, part in enumerate(parts, start=1):
            is_first = index == 1
            # content_jobs.title은 관리자 화면의 "등록 작업" 목록에 그대로
            # 뜬다. 24부를 등록하면 같은 제목이 24줄 늘어서서 어디서 멈췄는지
            # 알 수 없으므로, 여기에는 몇 번째 부인지까지 적는다. 오디오북
            # 행에 들어갈 진짜 제목은 work_title로 따로 넘긴다.
            job_title = work_title if is_single else \
                f"{work_title} · {index}/{len(parts)} {part['title'] or ''}".strip()
            job_items.append({
                **metadata,
                "title": job_title,
                "work_title": work_title,
                "content": part["content"],
                "audiobook_id": work_id if is_first else str(uuid.uuid4()),
                # 1부는 작품 대표 행이라 part_of가 비어 있다. 목록 쿼리는
                # 이 NULL 하나로 "작품"과 "부"를 가른다.
                "part_of": None if is_first else work_id,
                "part_number": None if is_single else index,
                "part_title": part["title"],
            })
    return job_items


async def store_library_item(supabase, admin_user_id: str, item: dict, job_id: str) -> str:
    """content_jobs 처리기가 호출하는 저장 함수(kind='library')."""
    status = item.get("status") if item.get("status") in LIBRARY_STATUSES else "review"
    # 큐잉 때 확정해 둔 id를 쓴다(_expand_to_job_items). 없으면 예전처럼
    # 새로 만든다 — 이 경로로 들어오는 오래된 작업이 남아 있을 수 있다.
    audiobook_id = item.get("audiobook_id") or str(uuid.uuid4())

    # ⚠️ 부의 공개 상태는 큐잉 때 정한 값이 아니라 "지금 작품이 어떤 상태인가"를
    # 따른다. 24부짜리는 합성에 20분 가까이 걸리는데, 그동안 관리자가 앞부분을
    # 확인하고 발행을 누르면 그 시점 이후에 만들어지는 부들만 review로 남는다.
    # 실제로 오디세이 등록에서 1~15부는 published, 16~24부는 review가 됐다.
    # 작품과 부의 상태는 어떤 경우에도 갈리면 안 된다.
    part_of = item.get("part_of")
    if part_of:
        try:
            work = supabase.table("audiobooks").select("library_status") \
                .eq("id", part_of).maybe_single().execute()
            if work and work.data and work.data.get("library_status") in LIBRARY_STATUSES:
                status = work.data["library_status"]
        except Exception:
            # 작품 행을 못 읽어도 부는 만들어야 한다. 그때는 큐잉 때의 값을
            # 그대로 쓰고, 어긋나면 관리자가 발행을 다시 누르면 전파된다.
            logger.exception("작품의 공개 상태를 읽지 못했습니다 part_of=%s", part_of)
    # 시리즈의 부는 작품명을 제목으로 갖는다. item["title"]은 관리자 작업
    # 목록에 보여줄 "오디세이 · 3/24 제3권" 쪽이라 그대로 쓰면 안 된다.
    title = item.get("work_title") or item["title"]
    audio_path, sentences = await synthesize_into_storage(
        supabase, admin_user_id, audiobook_id, item["content"], job_id
    )

    # 목록 카드에 재생시간/장 수를 보여주려고 미리 계산해 둔다 — 매번
    # sentences 파일을 내려받아 계산하면 목록 화면이 N배 느려진다.
    duration_seconds = round(max((s.get("end", 0) for s in sentences), default=0) / 1000)
    chapter_count = sum(1 for s in sentences if s.get("type") == "heading")

    try:
        supabase.table("audiobooks").insert({
            "id": audiobook_id,
            "user_id": admin_user_id,
            "title": title,
            "file_name": title,
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
            "library_part_of": item.get("part_of"),
            "library_part_number": item.get("part_number"),
            "library_part_title": item.get("part_title"),
        }).execute()
    except Exception:
        # 행이 없으면 이 파일들을 가리키는 것이 아무것도 없다.
        remove_audiobook_objects(supabase, admin_user_id, audiobook_id)
        raise
    return audiobook_id


@router.post("/api/admin/library")
async def add_library_items(payload: dict, background_tasks: BackgroundTasks, authorization: str = Header(None)):
    admin_user_id = require_admin_user(authorization)
    works = _parse_library_payload(payload.get("text") or "")
    items = _expand_to_job_items(works)

    # ⚠️ 순서대로 큐잉해야 1부가 먼저 합성된다(run_jobs는 순차 실행).
    # 정합성 자체는 id를 미리 확정해 둔 덕에 순서와 무관하게 보장되지만,
    # 1부부터 만들어지면 긴 시리즈의 앞부분을 합성이 끝나기 전에도 볼 수 있다.
    job_ids = queue_jobs(supabase_or_503(), "library", admin_user_id, items)
    background_tasks.add_task(run_jobs, job_ids)
    return {"queued": len(job_ids), "works": len(works)}


@router.get("/api/admin/library")
async def list_all_library_items(authorization: str = Header(None)):
    """상태(review/published) 상관없이 전체 작품을 관리자에게 보여준다 —
    /api/library(공개 목록)와 달리 published 필터를 걸지 않는다.

    공개 목록과 마찬가지로 부는 빼고 작품만 보여준다. 부까지 나오면 24권짜리
    하나가 관리 화면을 통째로 덮어 다른 작품의 공개 전환을 할 수 없다."""
    require_admin_user(authorization)
    supabase = supabase_or_503()
    try:
        rows = supabase.table("audiobooks") \
            .select("id, title, library_status, library_category, library_edition, "
                    "library_translator, library_source, library_rights, library_description, "
                    "library_part_number, created_at") \
            .eq("is_library", True).is_("library_part_of", "null") \
            .order("created_at", desc=True).execute().data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"작품 목록을 불러오지 못했습니다: {e}")

    stats = _part_stats(supabase, [row["id"] for row in rows])
    for row in rows:
        row["part_count"] = 1 if row.get("library_part_number") is None \
            else stats.get(row["id"], {}).get("count", 0) + 1
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

    supabase = supabase_or_503()
    try:
        supabase.table("audiobooks").update(changes) \
            .eq("id", audiobook_id).eq("is_library", True).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"작품을 수정하지 못했습니다: {e}")

    # ⚠️ 부에도 같은 값을 밀어 넣는다. 부는 목록에 안 나오지만 상세와 재생은
    # 부 행을 직접 읽으므로, 작품만 published로 바꾸고 부를 review로 두면
    # 목록에는 보이는데 재생이 되지 않는 작품이 만들어진다.
    #
    # 부 제목(library_part_title)은 건드리지 않는다 — 여기서 고치는 title은
    # 작품명이고, 부마다 다른 제목은 재등록으로만 바꾼다.
    part_changes = {key: value for key, value in changes.items()
                    if key in ("library_status", "title")}
    if part_changes:
        try:
            supabase.table("audiobooks").update(part_changes) \
                .eq("library_part_of", audiobook_id).execute()
        except Exception:
            # 작품 자체는 이미 바뀌었다. 부 전파가 실패했다고 400을 돌려주면
            # 관리자가 "실패했나?" 하고 다시 눌러 상태가 더 엉킨다.
            logger.exception("작품의 부에 변경을 전파하지 못했습니다 id=%s", audiobook_id)
    return {"updated": changes}


def _part_stats(supabase, work_ids: list[str]) -> dict[str, dict]:
    """작품 id → {"count": 딸린 부 수, "duration": 그 부들의 재생시간 합}.

    목록 카드에 "전 24부 · 약 7시간"을 띄우려면 부의 정보가 필요한데,
    작품마다 따로 조회하면 카드 수만큼 요청이 나간다(N+1). 한 번에 받아
    파이썬에서 묶는다.

    ⚠️ 여기서는 서명 URL을 만들지 않는다. 부까지 전부 서명하면 목록 한 번에
    수백 개를 서명하게 되는데, 목록 화면에서는 재생하지 않아 쓰이지 않는다.
    """
    if not work_ids:
        return {}
    try:
        rows = supabase.table("audiobooks") \
            .select("library_part_of, duration_seconds") \
            .in_("library_part_of", work_ids).execute().data or []
    except Exception:
        # 부 정보를 못 받아도 작품 목록 자체는 보여줘야 한다. 그때는 카드에
        # 부 수가 안 뜰 뿐이다.
        logger.exception("작품의 부 정보를 불러오지 못했습니다")
        return {}

    stats: dict[str, dict] = {}
    for row in rows:
        entry = stats.setdefault(row["library_part_of"], {"count": 0, "duration": 0})
        entry["count"] += 1
        entry["duration"] += row.get("duration_seconds") or 0
    return stats


def _with_part_summary(item: dict, work_row: dict, stats: dict | None) -> dict:
    """카드에 필요한 부 수와 총 재생시간을 항목에 붙인다.

    단권은 part_count가 1이고 total_duration_seconds가 자기 재생시간이다 —
    화면이 시리즈와 단권을 갈라 처리하지 않아도 되게 맞춰 둔다.
    """
    own_duration = work_row.get("duration_seconds") or 0
    if work_row.get("library_part_number") is None:
        item["part_count"] = 1
        item["total_duration_seconds"] = own_duration
        return item
    # 1부(작품 대표 행)는 stats에 없다. 자기 몫을 더해 준다.
    item["part_count"] = (stats or {}).get("count", 0) + 1
    item["total_duration_seconds"] = (stats or {}).get("duration", 0) + own_duration
    return item


@router.get("/api/library")
async def list_library():
    """공개된(published) 라이브러리 작품 목록. 로그인 여부와 무관하게 볼 수 있다.

    시리즈는 작품 하나로만 나온다 — 부는 library_part_of가 채워져 있어
    이 목록에 들어오지 않는다. 24권짜리를 등록해도 서점 화면이 그 작품으로
    도배되지 않는다.
    """
    supabase = supabase_or_503()
    try:
        rows = supabase.table("audiobooks").select("*") \
            .eq("is_library", True).eq("library_status", "published") \
            .is_("library_part_of", "null") \
            .order("created_at", desc=True).execute().data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"라이브러리를 불러오지 못했습니다: {e}")

    stats = _part_stats(supabase, [row["id"] for row in rows])

    items = []
    for row in rows:
        try:
            expanded = audiobook_items_with_urls(supabase, row["user_id"], [row])
        except Exception:
            continue
        items.extend(_with_part_summary(item, row, stats.get(row["id"])) for item in expanded)
    return {"library": items}


# ⚠️ 이 라우트는 반드시 "/api/library/{audiobook_id}"보다 먼저 등록해야 한다.
# FastAPI는 등록 순서대로 매칭하므로, 뒤에 두면 "saves"가 audiobook_id로
# 잡혀 UUID 캐스팅에서 터진다(실제로 그래서 이 엔드포인트는 추가된 이후
# 한 번도 동작한 적이 없었다).
@router.get("/api/library/saves")
async def list_library_saves(authorization: str = Header(None)):
    """내가 서재에 추가한 라이브러리 작품 목록."""
    user_id = require_user_id(authorization)
    supabase = supabase_or_503()
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
    supabase = supabase_or_503()
    try:
        rows = supabase.table("playback_history") \
            .select("audiobook_id, current_time_seconds") \
            .eq("user_id", user_id).execute().data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"재생 위치를 불러오지 못했습니다: {e}")
    return {"positions": {row["audiobook_id"]: row.get("current_time_seconds") or 0 for row in rows}}


def _load_parts(supabase, work_row: dict) -> list[dict]:
    """작품의 모든 부를 번호순으로 돌려준다. 단권이면 빈 목록.

    ⚠️ 1부는 작품 대표 행 자신이라 library_part_of 조회에 걸리지 않는다.
    목록 맨 앞에 직접 넣는다 — 빠뜨리면 재생목록이 2부부터 시작한다.

    합성이 아직 안 끝났거나 중간 부가 실패했으면 번호에 구멍이 난 채로
    돌아온다. 있는 것만이라도 들을 수 있는 편이 낫고, 실패한 부는 관리자
    화면에서 재시도하면 같은 자리에 메워진다.
    """
    if work_row.get("library_part_number") is None:
        return []
    try:
        rows = supabase.table("audiobooks").select("*") \
            .eq("library_part_of", work_row["id"]) \
            .order("library_part_number").execute().data or []
    except Exception:
        logger.exception("작품의 부를 불러오지 못했습니다 id=%s", work_row["id"])
        return []

    parts = []
    for row in [work_row, *rows]:
        try:
            expanded = audiobook_items_with_urls(supabase, row["user_id"], [row])
        except Exception:
            continue
        for entry in expanded:
            parts.append({
                "id": entry["id"],
                "part_number": row.get("library_part_number"),
                "part_title": row.get("library_part_title") or entry.get("title"),
                "duration_seconds": row.get("duration_seconds"),
                "audio_url": entry.get("audio_url"),
                "sentences_url": entry.get("sentences_url"),
            })
    return parts


@router.get("/api/library/{audiobook_id}")
async def get_library_item(audiobook_id: str):
    """작품 상세. published 상태인 작품만 조회할 수 있다.

    시리즈면 parts에 모든 부가 번호순으로 담겨 온다. 최상위 audio_url은
    1부의 것이라, 부를 모르는 기존 화면도 그대로 1부부터 재생한다.
    """
    supabase = supabase_or_503()
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

    item = items[0]
    item["parts"] = _load_parts(supabase, response.data)
    # 부를 실제로 세어 채운다 — 목록의 요약값과 달리 여기서는 이미 전부
    # 들고 있고, 합성이 덜 끝났으면 그 숫자가 진실이다.
    item["part_count"] = len(item["parts"]) or 1
    item["total_duration_seconds"] = sum(
        part.get("duration_seconds") or 0 for part in item["parts"]
    ) or (response.data.get("duration_seconds") or 0)
    return item


@router.post("/api/library/{audiobook_id}/save")
async def save_library_item(audiobook_id: str, authorization: str = Header(None)):
    user_id = require_user_id(authorization)
    supabase = supabase_or_503()
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
    supabase = supabase_or_503()
    try:
        supabase.table("library_saves").delete() \
            .eq("user_id", user_id).eq("audiobook_id", audiobook_id).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"내 서재 제거에 실패했습니다: {e}")
    return {"saved": False}
