"""요약기 테스트. Claude 호출은 전부 mock한다 — 실제 호출은 돈이 들고 결과가
매번 달라 테스트가 될 수 없다. 여기서 검증하는 것은 모델의 요약 품질이 아니라
"모델이 규칙을 어겼을 때 우리 코드가 어떻게 막는가"다.
"""
import pytest
from unittest.mock import AsyncMock, patch

import summarizer
from summarizer import Briefing, NewsItem, SUMMARY_MAX_CHARS


def _candidate(guid="g1", title="후보 제목"):
    return {
        "guid": guid,
        "title": title,
        "source": "연합뉴스",
        "url": "https://example.com/article",
        "content": "피드가 준 요약",
        "category": "economy",
    }


def _item(**overrides):
    base = {
        "title": "제목",
        "content": "본문",
        "source": "연합뉴스",
        "url": "https://example.com/article",
        "guid": "g1",
    }
    base.update(overrides)
    return NewsItem(**base)


def _mock_client(*responses):
    """messages.parse가 호출될 때마다 responses를 순서대로 돌려주는 가짜 클라이언트."""
    parse = AsyncMock(side_effect=[type("R", (), {"parsed_output": r})() for r in responses])
    client = type("C", (), {"messages": type("M", (), {"parse": parse})()})()
    return client, parse


@pytest.mark.asyncio
async def test_returns_items_from_the_model():
    client, _ = _mock_client(Briefing(items=[_item(title="첫 소식")]))

    with patch.object(summarizer, "_client", return_value=client):
        items = await summarizer.summarize_category("economy", [_candidate()])

    assert [item.title for item in items] == ["첫 소식"]


@pytest.mark.asyncio
async def test_no_candidates_makes_no_call():
    """후보가 없으면 부르지 않는다 — 빈 목록에 돈을 쓸 이유가 없다."""
    client, parse = _mock_client(Briefing(items=[]))

    with patch.object(summarizer, "_client", return_value=client):
        items = await summarizer.summarize_category("economy", [])

    assert items == []
    parse.assert_not_called()


@pytest.mark.asyncio
async def test_rejects_item_without_url():
    """링크가 없으면 원문으로 넘어갈 방법이 없다. 저장하지 않는다."""
    client, _ = _mock_client(Briefing(items=[_item(url=""), _item(title="정상")]))

    with patch.object(summarizer, "_client", return_value=client):
        items = await summarizer.summarize_category("economy", [_candidate()])

    assert [item.title for item in items] == ["정상"]


@pytest.mark.asyncio
async def test_rejects_item_without_source():
    """출처를 밝히지 못하는 뉴스는 내보내지 않는다."""
    client, _ = _mock_client(Briefing(items=[_item(source="   "), _item(title="정상")]))

    with patch.object(summarizer, "_client", return_value=client):
        items = await summarizer.summarize_category("economy", [_candidate()])

    assert [item.title for item in items] == ["정상"]


@pytest.mark.asyncio
async def test_retries_once_when_summary_too_long():
    """길이를 넘기면 자르지 않고 다시 시킨다 — 자르면 문장 중간에서 끊겨
    소리로 들을 때 특히 어색하다."""
    long_item = _item(title="긴 요약", content="가" * (SUMMARY_MAX_CHARS + 1))
    fixed = _item(title="긴 요약", content="짧게 고쳐 씀")
    client, parse = _mock_client(Briefing(items=[long_item]), Briefing(items=[fixed]))

    with patch.object(summarizer, "_client", return_value=client):
        items = await summarizer.summarize_category("economy", [_candidate()])

    assert parse.await_count == 2
    assert [item.content for item in items] == ["짧게 고쳐 씀"]


@pytest.mark.asyncio
async def test_drops_item_still_too_long_after_retry():
    """두 번째도 넘치면 그 항목만 버리고 나머지는 살린다 — 한 건 때문에
    카테고리 전체를 날리지 않는다."""
    too_long = _item(title="안 고쳐짐", content="가" * (SUMMARY_MAX_CHARS + 1))
    client, parse = _mock_client(
        Briefing(items=[too_long, _item(title="정상")]),
        Briefing(items=[too_long]),
    )

    with patch.object(summarizer, "_client", return_value=client):
        items = await summarizer.summarize_category("economy", [_candidate()])

    assert parse.await_count == 2
    assert [item.title for item in items] == ["정상"]


@pytest.mark.asyncio
async def test_unparsable_response_returns_what_was_accepted():
    """파싱이 실패해도 예외를 던지지 않는다 — 뉴스 등록 전체가 죽는 것보다
    그때까지 받아 둔 것을 돌려주는 편이 낫다."""
    client, _ = _mock_client(None)

    with patch.object(summarizer, "_client", return_value=client):
        items = await summarizer.summarize_category("economy", [_candidate()])

    assert items == []


@pytest.mark.asyncio
async def test_prompt_carries_limit_and_candidate_guids():
    """모델이 guid를 그대로 돌려줘야 저장 단계가 중복을 막을 수 있다 —
    후보 블록에 guid가 실제로 실리는지 확인한다."""
    client, parse = _mock_client(Briefing(items=[]))

    with patch.object(summarizer, "_client", return_value=client):
        await summarizer.summarize_category("economy", [_candidate(guid="unique-guid")], limit=3)

    kwargs = parse.await_args.kwargs
    assert "최대 3건" in kwargs["system"]
    assert "unique-guid" in kwargs["messages"][0]["content"]
    assert kwargs["model"] == summarizer.MODEL
