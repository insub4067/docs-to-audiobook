"""유튜브 자막 추출 /api/extract-youtube 테스트.

YouTubeTranscriptApi는 라우트 함수 안에서 지연 import하므로(다른 라우트의
trafilatura와 같은 패턴), 실제 정의 모듈(youtube_transcript_api)의 이름을
patch해야 한다 — 함수가 호출되는 시점에 그 모듈에서 새로 import해 오기
때문이다.
"""
import pytest
import httpx
from unittest.mock import patch, MagicMock
from main import app
from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled, VideoUnavailable


def _auth_headers():
    from auth import create_access_token
    token = create_access_token({"sub": "test_user_id"})
    return {"Authorization": f"Bearer {token}"}


class FakeSnippet:
    def __init__(self, text):
        self.text = text


class FakeTranscript:
    def __init__(self, segments):
        self._segments = segments

    def fetch(self):
        return self._segments


class FakeTranscriptList:
    def __init__(self, transcript, find_raises=None):
        self._transcript = transcript
        self._find_raises = find_raises

    def find_transcript(self, languages):
        if self._find_raises:
            raise self._find_raises
        return self._transcript

    def __iter__(self):
        return iter([self._transcript])


def _patch_transcript_api(transcript_list=None, list_raises=None):
    fake_api_class = MagicMock()
    if list_raises:
        fake_api_class.return_value.list.side_effect = list_raises
    else:
        fake_api_class.return_value.list.return_value = transcript_list
    return patch("youtube_transcript_api.YouTubeTranscriptApi", fake_api_class)


LONG_TEXT = "이것은 충분히 긴 자막 문장입니다. " * 10


@pytest.mark.asyncio
async def test_extract_youtube_requires_auth():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/extract-youtube", json={"url": "https://youtu.be/dQw4w9WgXcQ"})
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_extract_youtube_missing_url_field():
    with patch("routes.extract_youtube.require_user_id", return_value="test_user_id"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/extract-youtube", json={}, headers=_auth_headers())
            assert response.status_code == 400


@pytest.mark.asyncio
async def test_extract_youtube_rejects_invalid_url():
    with patch("routes.extract_youtube.require_user_id", return_value="test_user_id"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/extract-youtube", json={"url": "https://example.com/not-a-video"}, headers=_auth_headers()
            )
            assert response.status_code == 400
            assert "유튜브 링크" in response.json()["detail"]


@pytest.mark.asyncio
async def test_extract_youtube_success():
    transcript = FakeTranscript([FakeSnippet(LONG_TEXT), FakeSnippet("두 번째 문장입니다.")])
    transcript_list = FakeTranscriptList(transcript)
    fake_title_resp = MagicMock(ok=True)
    fake_title_resp.json.return_value = {"title": "테스트 영상 제목"}

    with patch("routes.extract_youtube.require_user_id", return_value="test_user_id"), \
         _patch_transcript_api(transcript_list=transcript_list), \
         patch("routes.extract_youtube.requests.get", return_value=fake_title_resp):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/extract-youtube", json={"url": "https://youtu.be/dQw4w9WgXcQ"}, headers=_auth_headers()
            )

    assert response.status_code == 200
    data = response.json()
    assert data["filename"] == "테스트 영상 제목"
    assert "충분히 긴 자막" in data["preview"]
    assert data["char_count"] > 50

    from state import text_storage
    text_storage.pop(data["text_id"], None)


@pytest.mark.asyncio
async def test_extract_youtube_falls_back_to_any_transcript_when_no_ko_en():
    # find_transcript(['ko','en'])가 실패해도(자막이 다른 언어뿐이어도)
    # 사용 가능한 첫 자막으로 대체해 완전히 막히지 않게 한다.
    transcript = FakeTranscript([FakeSnippet(LONG_TEXT)])
    transcript_list = FakeTranscriptList(transcript, find_raises=NoTranscriptFound("vid", ["ko", "en"], {}))
    fake_title_resp = MagicMock(ok=False)

    with patch("routes.extract_youtube.require_user_id", return_value="test_user_id"), \
         _patch_transcript_api(transcript_list=transcript_list), \
         patch("routes.extract_youtube.requests.get", return_value=fake_title_resp):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/extract-youtube", json={"url": "https://youtu.be/dQw4w9WgXcQ"}, headers=_auth_headers()
            )

    assert response.status_code == 200
    data = response.json()
    assert data["filename"] == "유튜브 영상"  # 제목 조회 실패 시 기본값

    from state import text_storage
    text_storage.pop(data["text_id"], None)


@pytest.mark.asyncio
async def test_extract_youtube_reports_disabled_transcripts():
    with patch("routes.extract_youtube.require_user_id", return_value="test_user_id"), \
         _patch_transcript_api(list_raises=TranscriptsDisabled("vid")):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/extract-youtube", json={"url": "https://youtu.be/dQw4w9WgXcQ"}, headers=_auth_headers()
            )

    assert response.status_code == 422
    assert "자막을 지원하지 않습니다" in response.json()["detail"]


@pytest.mark.asyncio
async def test_extract_youtube_reports_video_unavailable():
    with patch("routes.extract_youtube.require_user_id", return_value="test_user_id"), \
         _patch_transcript_api(list_raises=VideoUnavailable("vid")):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/extract-youtube", json={"url": "https://youtu.be/dQw4w9WgXcQ"}, headers=_auth_headers()
            )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_extract_youtube_reports_generic_failure_as_502():
    with patch("routes.extract_youtube.require_user_id", return_value="test_user_id"), \
         _patch_transcript_api(list_raises=RuntimeError("boom")):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/extract-youtube", json={"url": "https://youtu.be/dQw4w9WgXcQ"}, headers=_auth_headers()
            )

    assert response.status_code == 502


@pytest.mark.asyncio
async def test_extract_youtube_rejects_too_short_transcript():
    transcript = FakeTranscript([FakeSnippet("짧음")])
    transcript_list = FakeTranscriptList(transcript)

    with patch("routes.extract_youtube.require_user_id", return_value="test_user_id"), \
         _patch_transcript_api(transcript_list=transcript_list):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/extract-youtube", json={"url": "https://youtu.be/dQw4w9WgXcQ"}, headers=_auth_headers()
            )

    assert response.status_code == 422
    assert "너무 짧아" in response.json()["detail"]


@pytest.mark.asyncio
async def test_extract_youtube_rejects_text_too_long():
    from state import MAX_SYNTH_CHARS

    transcript = FakeTranscript([FakeSnippet("가" * (MAX_SYNTH_CHARS + 1))])
    transcript_list = FakeTranscriptList(transcript)

    with patch("routes.extract_youtube.require_user_id", return_value="test_user_id"), \
         _patch_transcript_api(transcript_list=transcript_list):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/extract-youtube", json={"url": "https://youtu.be/dQw4w9WgXcQ"}, headers=_auth_headers()
            )

    assert response.status_code == 413


def test_extract_youtube_video_id_parsing():
    from routes.extract_youtube import _extract_youtube_video_id

    assert _extract_youtube_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert _extract_youtube_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert _extract_youtube_video_id("https://youtu.be/dQw4w9WgXcQ?si=abc") == "dQw4w9WgXcQ"
    assert _extract_youtube_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10s") == "dQw4w9WgXcQ"
    assert _extract_youtube_video_id("https://m.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert _extract_youtube_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert _extract_youtube_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert _extract_youtube_video_id("not a url") is None
    assert _extract_youtube_video_id("https://example.com/watch?v=x") is None
