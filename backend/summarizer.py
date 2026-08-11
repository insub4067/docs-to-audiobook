"""RSS 후보 목록을 Claude로 선별·요약해 방송용 뉴스 항목을 만든다.

news_sources.py가 모아온 후보(제목 + 피드 요약)를 받아 카테고리당 한 번 호출로
"오늘 들을 만한 N건"을 고른다. 선별·중복 판정·요약을 한 번에 시키는 이유는
설계 §4.1에 있다 — 세 단계로 쪼개면 호출이 3배가 되는데, 중복 판정은 후보
전체를 한꺼번에 봐야 제대로 되므로 쪼갤 이득이 없다.

⚠️ 이 모듈은 저장하지 않는다. 반환한 항목을 routes/news.py가 받아 합성·저장한다.
"""
import logging
import os

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# 귀로 듣는 글이라 화면에서 읽는 것보다 짧아야 한다. 400자면 보통 1분 안쪽으로
# 읽히고, 한 번에 여러 건을 이어 들어도 지치지 않는다.
SUMMARY_MAX_CHARS = 400

# 카테고리당 기본 선별 건수. 호출부가 바꿀 수 있다.
DEFAULT_LIMIT = 5

# 요약이 상한을 넘겼을 때 다시 시켜보는 횟수. 두 번째도 넘치면 그 항목만 버린다
# — 자르면 문장 중간에서 끊겨 소리로 들을 때 특히 어색하다.
MAX_LENGTH_RETRIES = 1

MODEL = "claude-opus-5"

# ⚠️ thinking과 응답이 같은 max_tokens를 나눠 쓴다. Claude Opus 5는 thinking이
# 기본으로 켜져 있어서, 응답 길이만 보고 빠듯하게 잡으면 답이 중간에 잘린다.
# 5건 × 400자면 응답 자체는 3천 토큰이면 되지만 여유를 크게 둔다.
MAX_TOKENS = 16000

SYSTEM_PROMPT = """당신은 오디오 뉴스 브리핑의 편집자다. 후보 기사 목록을 받아
그날 들을 만한 것을 골라 짧게 다시 쓴다.

무엇을 고르는가:
- 중요한 순서로 최대 {limit}건. 후보가 그보다 적거나 들을 만한 것이 적으면 적게 골라도 된다.
- 같은 사건을 다룬 기사가 여러 건이면 하나만 남긴다. 제목이 달라도 같은 일이면 같은 사건이다.
- 단신·홍보성 기사·특정 종목 추천은 거른다.

어떻게 쓰는가:
- 눈으로 읽는 글이 아니라 귀로 듣는 글이다. 한 문장을 길게 늘이지 말고, 숫자는 말하듯 쓴다.
- {max_chars}자를 넘기지 않는다.
- 원문 문장을 그대로 옮기지 않는다. 사실만 가져와 새로 쓴다.
- 제목도 들었을 때 무슨 일인지 알 수 있게 다시 쓴다.
- 없는 사실을 지어내지 않는다. 후보에 있는 내용만 쓴다.

source와 url은 입력에 있는 값을 그대로 옮긴다. 고치거나 지어내지 않는다."""


class NewsItem(BaseModel):
    """선별·요약된 뉴스 한 건. 저장 단계가 이 모양을 그대로 받는다."""

    title: str
    content: str
    source: str
    url: str
    guid: str


class Briefing(BaseModel):
    items: list[NewsItem]


def _client():
    """호출 시점에 만든다 — import 시점에 만들면 키가 없는 환경(테스트, 아직
    시크릿을 안 넣은 배포)에서 모듈을 못 읽는다."""
    from anthropic import AsyncAnthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY가 설정되지 않았습니다.")
    return AsyncAnthropic(api_key=api_key)


def _candidates_block(candidates: list[dict]) -> str:
    """후보를 프롬프트에 넣을 형태로 편다. guid를 함께 주는 이유는, 고른 항목이
    어느 후보였는지 모델이 그대로 돌려줘야 저장 단계가 중복을 막을 수 있어서다."""
    lines = []
    for candidate in candidates:
        lines.append(
            f"- guid: {candidate['guid']}\n"
            f"  제목: {candidate['title']}\n"
            f"  출처: {candidate['source']}\n"
            f"  링크: {candidate['url']}\n"
            f"  요약: {candidate['content']}"
        )
    return "\n".join(lines)


def _is_usable(item: NewsItem) -> bool:
    """출처와 링크가 없으면 저장하지 않는다. 어디서 온 이야기인지 밝히지 못하는
    뉴스를 내보내면 안 되고, 링크는 화면에서 원문으로 넘어가는 유일한 통로다."""
    if not item.url.strip() or not item.source.strip():
        logger.warning("출처 또는 링크가 없어 버림: %r", item.title)
        return False
    return True


async def summarize_category(
    category: str,
    candidates: list[dict],
    limit: int = DEFAULT_LIMIT,
) -> list[NewsItem]:
    """한 카테고리의 후보를 골라 요약한다. 호출은 카테고리당 한 번이다.

    길이를 넘긴 항목은 한 번 다시 시키고, 그래도 넘치면 그 항목만 버린다.
    출처나 링크가 없는 항목도 버린다 — 부분적으로라도 쓸 수 있는 결과를
    돌려주는 편이, 한 건 때문에 카테고리 전체를 날리는 것보다 낫다.
    """
    if not candidates:
        return []

    client = _client()
    system = SYSTEM_PROMPT.format(limit=limit, max_chars=SUMMARY_MAX_CHARS)
    user = (
        f"카테고리: {category}\n\n"
        f"후보 {len(candidates)}건:\n{_candidates_block(candidates)}"
    )
    messages = [{"role": "user", "content": user}]

    accepted: list[NewsItem] = []
    for attempt in range(MAX_LENGTH_RETRIES + 1):
        response = await client.messages.parse(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            output_config={"effort": "medium"},
            system=system,
            messages=messages,
            output_format=Briefing,
        )
        briefing = response.parsed_output
        if briefing is None:
            logger.warning("요약 결과를 파싱하지 못했습니다 (category=%s)", category)
            return accepted

        too_long = []
        for item in briefing.items:
            if not _is_usable(item):
                continue
            if len(item.content) > SUMMARY_MAX_CHARS:
                too_long.append(item)
                continue
            accepted.append(item)

        if not too_long:
            break
        if attempt == MAX_LENGTH_RETRIES:
            for item in too_long:
                logger.warning(
                    "%d자를 넘겨 버림 (%d자): %r", SUMMARY_MAX_CHARS, len(item.content), item.title
                )
            break

        # 넘친 것만 다시 시킨다. 통과한 항목까지 다시 만들게 하면 이미 좋은
        # 요약이 바뀌고 토큰도 두 번 든다.
        messages = [
            {"role": "user", "content": user},
            {
                "role": "user",
                "content": (
                    f"다음 항목의 요약이 {SUMMARY_MAX_CHARS}자를 넘었습니다. "
                    f"이 항목만 다시 골라 {SUMMARY_MAX_CHARS}자 안으로 써 주세요: "
                    + ", ".join(item.title for item in too_long)
                ),
            },
        ]

    return accepted
