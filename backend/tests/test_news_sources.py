"""RSS 수집(news_sources.py) 테스트.

feedparser.parse는 네트워크를 타므로 패치한다. DB(news_sources 조회)는
supabase 체인을 MagicMock으로 흉내 낸다.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import news_sources


def _feed(entries, bozo=0, bozo_exception=None):
    """feedparser.parse의 반환을 흉내 낸다. .entries/.bozo/.get을 쓴다."""
    feed = MagicMock()
    feed.entries = entries
    feed.bozo = bozo
    feed.get.return_value = bozo_exception
    return feed


def _entry(**kwargs):
    """feedparser 항목은 .get을 지원하는 dict-유사 객체다."""
    return kwargs


def _sources_supabase(rows):
    """news_sources.select(...).eq(...).eq(...).execute().data 체인을 흉내."""
    supabase = MagicMock()
    query = supabase.table.return_value.select.return_value
    query.eq.return_value = query          # .eq()가 자기 자신을 돌려줘 체이닝
    query.execute.return_value = SimpleNamespace(data=rows)
    return supabase


def test_collect_gathers_candidates_from_all_sources():
    supabase = _sources_supabase([
        {"category": "경제", "name": "Reuters", "feed_url": "https://a.example/rss"},
        {"category": "경제", "name": "Bloomberg", "feed_url": "https://b.example/rss"},
    ])
    feeds = {
        "https://a.example/rss": _feed([_entry(title="달러 약세", link="https://a/1", summary="본문 A")]),
        "https://b.example/rss": _feed([_entry(title="금값 급등", link="https://b/1", summary="본문 B")]),
    }

    with patch("news_sources.feedparser.parse", side_effect=lambda url: feeds[url]):
        candidates = news_sources.collect_candidates(supabase)

    assert [c["title"] for c in candidates] == ["달러 약세", "금값 급등"]
    assert [c["source"] for c in candidates] == ["Reuters", "Bloomberg"]
    assert candidates[0]["category"] == "경제"


def test_collect_continues_when_one_feed_fails():
    """피드 하나가 예외를 던져도 나머지 소스는 수집돼야 한다."""
    supabase = _sources_supabase([
        {"category": "경제", "name": "Broken", "feed_url": "https://broken.example/rss"},
        {"category": "경제", "name": "Reuters", "feed_url": "https://ok.example/rss"},
    ])

    def flaky_parse(url):
        if "broken" in url:
            raise RuntimeError("네트워크 실패")
        return _feed([_entry(title="정상 뉴스", link="https://ok/1", summary="본문")])

    with patch("news_sources.feedparser.parse", side_effect=flaky_parse):
        candidates = news_sources.collect_candidates(supabase)

    assert [c["title"] for c in candidates] == ["정상 뉴스"]


def test_collect_skips_disabled_sources_via_query_filter():
    """enabled=false 소스는 DB 쿼리 단계에서 걸러진다(.eq('enabled', True))."""
    supabase = _sources_supabase([])
    with patch("news_sources.feedparser.parse") as parse:
        candidates = news_sources.collect_candidates(supabase)

    assert candidates == []
    parse.assert_not_called()
    eq_calls = [c.args for c in supabase.table.return_value.select.return_value.eq.call_args_list]
    assert ("enabled", True) in eq_calls


def test_collect_filters_by_category_when_given():
    supabase = _sources_supabase([])
    with patch("news_sources.feedparser.parse"):
        news_sources.collect_candidates(supabase, category="AI")

    eq_calls = [c.args for c in supabase.table.return_value.select.return_value.eq.call_args_list]
    assert ("category", "AI") in eq_calls


def test_entry_without_title_or_link_is_dropped():
    supabase = _sources_supabase([
        {"category": "경제", "name": "Reuters", "feed_url": "https://a.example/rss"},
    ])
    feed = _feed([
        _entry(title="제목만", summary="본문"),                       # link 없음 → 버림
        _entry(link="https://a/2", summary="본문"),                   # title 없음 → 버림
        _entry(title="정상", link="https://a/3", summary="본문"),
    ])

    with patch("news_sources.feedparser.parse", return_value=feed):
        candidates = news_sources.collect_candidates(supabase)

    assert [c["title"] for c in candidates] == ["정상"]


def test_guid_falls_back_to_link_when_missing():
    supabase = _sources_supabase([
        {"category": "경제", "name": "Reuters", "feed_url": "https://a.example/rss"},
    ])
    feed = _feed([
        _entry(title="id 있음", link="https://a/1", id="guid-1", summary="x"),
        _entry(title="id 없음", link="https://a/2", summary="x"),
    ])

    with patch("news_sources.feedparser.parse", return_value=feed):
        candidates = news_sources.collect_candidates(supabase)

    assert candidates[0]["guid"] == "guid-1"
    assert candidates[1]["guid"] == "https://a/2"


def test_html_tags_are_stripped_from_summary():
    supabase = _sources_supabase([
        {"category": "경제", "name": "Reuters", "feed_url": "https://a.example/rss"},
    ])
    feed = _feed([
        _entry(title="뉴스", link="https://a/1",
               summary="<p>본문 <a href='x'>링크</a>입니다.</p>"),
    ])

    with patch("news_sources.feedparser.parse", return_value=feed):
        candidates = news_sources.collect_candidates(supabase)

    assert candidates[0]["content"] == "본문 링크입니다."


def test_caps_entries_per_source():
    supabase = _sources_supabase([
        {"category": "경제", "name": "Reuters", "feed_url": "https://a.example/rss"},
    ])
    many = [_entry(title=f"뉴스{i}", link=f"https://a/{i}", summary="x") for i in range(30)]
    feed = _feed(many)

    with patch("news_sources.feedparser.parse", return_value=feed):
        candidates = news_sources.collect_candidates(supabase)

    assert len(candidates) == news_sources.MAX_ENTRIES_PER_SOURCE


def test_bozo_feed_with_no_entries_is_skipped():
    """파싱이 통째로 실패하면(bozo + entries 없음) 그 소스는 건너뛴다."""
    supabase = _sources_supabase([
        {"category": "경제", "name": "Reuters", "feed_url": "https://a.example/rss"},
    ])
    feed = _feed([], bozo=1, bozo_exception="malformed XML")

    with patch("news_sources.feedparser.parse", return_value=feed):
        candidates = news_sources.collect_candidates(supabase)

    assert candidates == []
