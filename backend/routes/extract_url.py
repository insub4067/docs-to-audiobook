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
import threading
import ipaddress
import requests
from urllib.parse import urlparse, urljoin
from fastapi import APIRouter, Request, HTTPException, Header

from state import require_user_id, enforce_rate_limit, text_storage, too_large

router = APIRouter()

# URL에서 기사를 가져올 때의 상한. 파일 업로드와 동일한 기준을 쓴다.
MAX_URL_FETCH_BYTES = 10 * 1024 * 1024
URL_FETCH_TIMEOUT_SEC = 10
URL_FETCH_MAX_REDIRECTS = 5


# DNS 재바인딩 방어 —
#
# 검사한 주소와 실제로 연결하는 주소가 같아야 의미가 있다. 예전에는
# getaddrinfo로 검사한 뒤 requests가 **다시** 조회했다. 그 사이 권한 있는
# 공격자의 DNS가 답을 바꾸면(첫 조회 공인 IP, 두 번째 조회 169.254.169.254)
# 검사를 통과한 채로 내부망에 연결된다.
#
# 그래서 검사에 쓴 주소를 그대로 고정해서 연결한다. URL의 호스트명을 IP로
# 바꿔치기하는 방법도 있지만 그러면 TLS 인증서 검증과 SNI가 깨진다. 대신
# 이름 해석 단계만 가로채, 호스트명은 그대로 두고 주소만 고정한다.
#
# 전역 socket.getaddrinfo를 교체하지만, 이 스레드에 고정 항목이 등록된
# 호스트에만 개입하고 나머지는 원래 함수로 그대로 넘긴다. URL 가져오기는
# asyncio.to_thread로 자기 스레드에서 돌기 때문에(extract_url 참고) 스레드
# 로컬이면 동시 요청끼리 서로의 고정값을 볼 수 없다.
_system_getaddrinfo = socket.getaddrinfo
_pinned = threading.local()


def _pinning_getaddrinfo(host, port, *args, **kwargs):
    entries = getattr(_pinned, "by_host", {}).get(host)
    if entries is None:
        return _system_getaddrinfo(host, port, *args, **kwargs)
    # 검사 때 받아 둔 주소를 그대로 쓰되 포트만 이번 요청 것으로 바꾼다.
    return [
        (family, socket.SOCK_STREAM, proto, canonname, (sockaddr[0], port) + tuple(sockaddr[2:]))
        for family, _socktype, proto, canonname, sockaddr in entries
    ]


socket.getaddrinfo = _pinning_getaddrinfo


def _is_public_address(raw_address: str) -> bool:
    """사설/루프백/링크로컬 대역과 클라우드 메타데이터 엔드포인트
    (169.254.169.254)를 막는다. 후자는 is_private로 안 잡혀서 따로 확인한다."""
    ip = ipaddress.ip_address(raw_address)
    if (ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_multicast or ip.is_reserved or ip.is_unspecified):
        return False
    return str(ip) != "169.254.169.254"


def _pin_safe_public_host(hostname: str) -> bool:
    """호스트명이 가리키는 IP가 전부 공인망이면, 그 주소들을 이 스레드에
    고정하고 True를 돌려준다. 이후 이 호스트로 나가는 연결은 다시 조회하지
    않고 여기서 검사한 주소만 쓴다."""
    try:
        entries = _system_getaddrinfo(hostname, None, 0, socket.SOCK_STREAM)
    except socket.gaierror:
        return False
    if not entries:
        return False
    for entry in entries:
        if not _is_public_address(entry[4][0]):
            return False

    if not hasattr(_pinned, "by_host"):
        _pinned.by_host = {}
    _pinned.by_host[hostname] = entries
    return True


def _clear_pinned_hosts() -> None:
    getattr(_pinned, "by_host", {}).clear()


def _fetch_url_safely(url: str) -> requests.Response:
    """스킴/호스트를 검증하며 요청하고, 리다이렉트는 직접 따라가며 매 홉마다
    다시 검증한다. requests의 allow_redirects=True를 쓰면 최종 목적지만
    보게 되어, 공인 IP로 한 번 응답한 뒤 내부망으로 리다이렉트하는 공격을
    놓칠 수 있다.

    매 홉의 검사 결과는 이 스레드에 고정되고, 실제 연결은 그 주소로만 나간다
    (_pin_safe_public_host 참고) — 검사와 연결 사이에 DNS 답이 바뀌어도
    소용없게 만든다."""
    try:
        return _fetch_following_redirects(url)
    finally:
        # 고정은 이 요청 동안만 유효하다. 스레드는 풀에서 재사용되므로
        # 남겨두면 다음 요청이 낡은 주소로 나간다.
        _clear_pinned_hosts()


def _fetch_following_redirects(url: str) -> requests.Response:
    for _ in range(URL_FETCH_MAX_REDIRECTS + 1):
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise HTTPException(status_code=400, detail="http/https 주소만 지원합니다.")
        if not parsed.hostname:
            raise HTTPException(status_code=400, detail="올바른 URL이 아닙니다.")
        if not _pin_safe_public_host(parsed.hostname):
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
                raise too_large(MAX_URL_FETCH_BYTES)
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
