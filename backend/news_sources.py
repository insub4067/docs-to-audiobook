"""RSS 피드에서 뉴스 후보를 수집한다.

저작권·SSRF 때문에 임의 URL을 긁지 않는다. 관리자가 news_sources 테이블에
등록한 피드에서만, 그것도 기사 본문이 아니라 피드가 스스로 공개한 제목과
요약(title/summary)만 가져온다 — 본문 전문 추출(extract_url.py)은 쓰지 않는다.
자세한 근거는 docs/product/2026-08-11-step0-curation-automation-design.md.

여기서 하는 일은 수집까지다. 후보 dict를 그대로 요약기(summarizer.py)에 넘기고,
선별·요약·중복 판정은 그쪽에서 한다.
"""
import logging
import re

import feedparser

logger = logging.getLogger(__name__)

# 소스 하나에서 가져올 최근 항목 수. 피드는 보통 최신순이라 앞에서 자른다.
# 후보가 너무 많으면 요약기 입력 토큰만 커지고 품질은 나아지지 않는다.
MAX_ENTRIES_PER_SOURCE = 15

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    """RSS summary에는 <p>, <a> 같은 태그가 섞여 온다. 요약기에 넘기기 전에
    태그만 벗겨 토큰을 아끼고 화면 깨짐을 막는다."""
    return re.sub(r"\s+", " ", _HTML_TAG_RE.sub("", text)).strip()


def _entry_to_candidate(entry, source: dict) -> dict | None:
    """feedparser 항목을 후보 dict로 바꾼다. 제목이나 링크가 없으면 버린다
    — 링크는 출처 표기에 반드시 필요하고, 제목 없는 항목은 쓸 수 없다."""
    title = (entry.get("title") or "").strip()
    link = (entry.get("link") or "").strip()
    if not title or not link:
        return None

    summary = entry.get("summary") or entry.get("description") or ""
    return {
        "title": title,
        "content": _strip_html(summary),
        "source": source["name"],
        "url": link,
        # guid가 없는 피드가 있다 — 그럴 땐 링크가 사실상 식별자다.
        "guid": (entry.get("id") or link).strip(),
        "category": source["category"],
    }


def _candidates_from_source(source: dict) -> list[dict]:
    """피드 하나에서 후보를 뽑는다. 이 피드가 죽어도 나머지 수집은 계속돼야
    하므로 예외를 여기서 삼키고 빈 목록을 돌려준다."""
    try:
        parsed = feedparser.parse(source["feed_url"])
    except Exception:
        logger.exception("RSS 피드를 불러오지 못했습니다 feed=%s", source["feed_url"])
        return []

    # feedparser는 네트워크·파싱 오류를 예외 대신 bozo 플래그로 알린다.
    # entries가 비어 있지 않으면 부분 파싱이라도 쓴다.
    if parsed.bozo and not parsed.entries:
        logger.warning(
            "RSS 피드 파싱 실패 feed=%s error=%s",
            source["feed_url"], parsed.get("bozo_exception"),
        )
        return []

    candidates = []
    for entry in parsed.entries[:MAX_ENTRIES_PER_SOURCE]:
        candidate = _entry_to_candidate(entry, source)
        if candidate:
            candidates.append(candidate)
    return candidates


def _enabled_sources(supabase, category: str | None) -> list[dict]:
    query = supabase.table("news_sources").select("category, name, feed_url") \
        .eq("enabled", True)
    if category is not None:
        query = query.eq("category", category)
    return query.execute().data or []


def collect_candidates(supabase, category: str | None = None) -> list[dict]:
    """등록된(enabled) 소스 전부에서 후보를 모아 돌려준다. category를 주면
    그 카테고리만. 피드 하나가 죽어도 나머지는 수집한다."""
    candidates = []
    for source in _enabled_sources(supabase, category):
        candidates.extend(_candidates_from_source(source))
    return candidates
