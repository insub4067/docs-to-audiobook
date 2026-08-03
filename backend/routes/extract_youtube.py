"""유튜브 영상에서 자막(스크립트) 가져오기.

extract_url과 마찬가지로 서버가 외부(유튜브)로 요청을 대신 나가므로
남용을 막기 위해 로그인을 요구한다. 다만 대상 호스트가 유튜브로
고정되어 있어(URL에서 videoId만 뽑아 쓴다) extract_url의 SSRF 방어
로직(임의 호스트 검증)은 필요 없다.
"""
import time
import uuid
import requests
from urllib.parse import urlparse, parse_qs
from fastapi import APIRouter, Request, HTTPException, Header

from state import require_user_id, enforce_rate_limit, text_storage, upload_limit_for, synth_limit_for

router = APIRouter()

TITLE_FETCH_TIMEOUT_SEC = 5


def _extract_youtube_video_id(url: str) -> str | None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.").removeprefix("m.")

    if host == "youtu.be":
        video_id = parsed.path.lstrip("/").split("/")[0]
        return video_id or None

    if host in ("youtube.com", "youtube-nocookie.com"):
        if parsed.path == "/watch":
            return (parse_qs(parsed.query).get("v") or [None])[0]
        for prefix in ("/shorts/", "/embed/", "/live/"):
            if parsed.path.startswith(prefix):
                video_id = parsed.path[len(prefix):].split("/")[0]
                return video_id or None

    return None


def _fetch_video_title(video_id: str) -> str:
    """oEmbed는 API 키 없이 쓸 수 있는 유튜브 공식 엔드포인트다.
    실패해도 자막 추출 자체를 막을 이유는 아니라 기본 제목으로 넘어간다."""
    try:
        resp = requests.get(
            "https://www.youtube.com/oembed",
            params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
            timeout=TITLE_FETCH_TIMEOUT_SEC,
        )
        if resp.ok:
            title = (resp.json() or {}).get("title")
            if title:
                return title
    except requests.RequestException:
        pass
    return "유튜브 영상"


@router.post("/api/extract-youtube")
async def extract_youtube(request: Request, payload: dict, authorization: str = Header(None)):
    require_user_id(authorization)
    enforce_rate_limit(request, "extract_youtube", limit=30, window_sec=600)

    url = (payload.get("url") or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="유튜브 링크를 입력해 주세요.")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    video_id = _extract_youtube_video_id(url)
    if not video_id:
        raise HTTPException(status_code=400, detail="올바른 유튜브 링크가 아닙니다.")

    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled, VideoUnavailable

    try:
        transcript_list = YouTubeTranscriptApi().list(video_id)
        try:
            transcript = transcript_list.find_transcript(["ko", "en"])
        except NoTranscriptFound:
            transcript = next(iter(transcript_list))
        fetched = transcript.fetch()
    except TranscriptsDisabled:
        raise HTTPException(status_code=422, detail="이 영상은 자막을 지원하지 않습니다.")
    except VideoUnavailable:
        raise HTTPException(status_code=404, detail="영상을 찾을 수 없습니다. 링크를 확인해 주세요.")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="자막을 가져오지 못했습니다. 잠시 후 다시 시도해 주세요.",
        )

    text = " ".join(snippet.text.strip() for snippet in fetched if snippet.text.strip())
    if not text or len(text.strip()) < 50:
        raise HTTPException(status_code=422, detail="자막 내용이 너무 짧아 오디오북을 만들 수 없습니다.")

    max_upload_bytes = upload_limit_for(authorization)
    max_synth_chars = synth_limit_for(max_upload_bytes)
    if len(text) > max_synth_chars:
        raise HTTPException(
            status_code=413,
            detail=f"자막이 너무 깁니다. 최대 {max_synth_chars:,}자까지 지원합니다.",
        )

    title = _fetch_video_title(video_id)

    file_id = str(uuid.uuid4())
    text_storage[file_id] = {
        "filename": title,
        "text": text,
        "char_count": len(text),
        "max_synth_chars": max_synth_chars,
        "created_at": time.time(),
        "access_token": uuid.uuid4().hex,
    }

    preview_len = min(500, len(text))
    return {
        "text_id": file_id,
        "filename": title,
        "char_count": len(text),
        "preview": text[:preview_len] + ("..." if len(text) > preview_len else ""),
        "text_access_token": text_storage[file_id]["access_token"],
    }
