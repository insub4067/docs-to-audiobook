"""URL에서 기사 가져오기.

파일 업로드와 달리 서버가 사용자가 지정한 아무 주소로나 요청을 대신
나가야 하므로 SSRF(서버를 이용한 내부망 접근/스캔) 위험이 있다. 그래서
파일 업로드와 달리 로그인을 요구한다(무인증 오픈 프록시가 되는 것을
막는다) — synthesize와 동일한 취급이다.
"""
import asyncio
import time
import uuid
import socket
import ipaddress
import requests
from urllib.parse import urlparse, urljoin
from fastapi import APIRouter, Request, HTTPException, Header

from state import require_user_id, enforce_rate_limit, text_storage, _too_large

router = APIRouter()

# URL에서 기사를 가져올 때의 상한. 파일 업로드와 동일한 기준을 쓴다.
MAX_URL_FETCH_BYTES = 10 * 1024 * 1024
URL_FETCH_TIMEOUT_SEC = 10
URL_FETCH_MAX_REDIRECTS = 5


def _is_safe_public_host(hostname: str) -> bool:
    """호스트명이 가리키는 IP가 전부 공인망인지 확인한다.

    사설/루프백/링크로컬 대역과 클라우드 메타데이터 엔드포인트
    (169.254.169.254)를 막는다. 후자는 is_private로 안 잡혀서 따로 확인한다.
    """
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_multicast or ip.is_reserved or ip.is_unspecified):
            return False
        if str(ip) == "169.254.169.254":
            return False
    return True


def _fetch_url_safely(url: str) -> requests.Response:
    """스킴/호스트를 검증하며 요청하고, 리다이렉트는 직접 따라가며 매 홉마다
    다시 검증한다. requests의 allow_redirects=True를 쓰면 최종 목적지만
    보게 되어, 공인 IP로 한 번 응답한 뒤 내부망으로 리다이렉트하는 공격을
    놓칠 수 있다."""
    for _ in range(URL_FETCH_MAX_REDIRECTS + 1):
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise HTTPException(status_code=400, detail="http/https 주소만 지원합니다.")
        if not parsed.hostname:
            raise HTTPException(status_code=400, detail="올바른 URL이 아닙니다.")
        if not _is_safe_public_host(parsed.hostname):
            raise HTTPException(status_code=400, detail="내부망 주소는 요청할 수 없습니다.")

        resp = requests.get(
            url,
            timeout=URL_FETCH_TIMEOUT_SEC,
            allow_redirects=False,
            headers={"User-Agent": "Mozilla/5.0 (compatible; docs-to-audiobook/1.0)"},
            stream=True,
        )
        if resp.status_code in (301, 302, 303, 307, 308) and resp.headers.get("Location"):
            next_url = urljoin(url, resp.headers["Location"])
            resp.close()
            url = next_url
            continue
        return resp
    raise HTTPException(status_code=400, detail="리다이렉트가 너무 많습니다.")


@router.post("/api/extract-url")
async def extract_url(request: Request, payload: dict, authorization: str = Header(None)):
    require_user_id(authorization)
    enforce_rate_limit(request, "extract_url", limit=30, window_sec=600)

    url = (payload.get("url") or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL을 입력해 주세요.")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        resp = await asyncio.to_thread(_fetch_url_safely, url)
    except requests.Timeout:
        raise HTTPException(
            status_code=504,
            detail="외부 페이지가 제한 시간 안에 응답하지 않았습니다. 잠시 후 다시 시도해 주세요.",
        )
    except requests.RequestException:
        raise HTTPException(status_code=400, detail="페이지를 가져오지 못했습니다. 주소를 확인해 주세요.")

    try:
        content_type = resp.headers.get("Content-Type", "")
        if "html" not in content_type.lower():
            raise HTTPException(status_code=400, detail="HTML 페이지만 지원합니다.")

        # 상한을 넘으면 즉시 중단한다 (read_upload_limited와 같은 패턴)
        chunks = []
        total = 0
        for chunk in resp.iter_content(chunk_size=64 * 1024):
            total += len(chunk)
            if total > MAX_URL_FETCH_BYTES:
                raise _too_large(MAX_URL_FETCH_BYTES)
            chunks.append(chunk)
        page_bytes = b"".join(chunks)
    except HTTPException:
        raise
    except requests.RequestException:
        raise HTTPException(status_code=400, detail="페이지를 가져오지 못했습니다. 주소를 확인해 주세요.")
    finally:
        resp.close()

    import trafilatura

    text = trafilatura.extract(page_bytes, include_comments=False, include_tables=False, favor_precision=True)

    if not text or len(text.strip()) < 200:
        raise HTTPException(
            status_code=422,
            detail="본문을 추출하지 못했습니다. 자바스크립트로 내용을 그리는 페이지는 아직 지원하지 않습니다.",
        )

    meta = trafilatura.extract_metadata(page_bytes)
    title = (meta.title if meta and meta.title else urlparse(url).hostname) or "제목 없음"

    file_id = str(uuid.uuid4())
    text_storage[file_id] = {
        "filename": title,
        "text": text,
        "char_count": len(text),
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
