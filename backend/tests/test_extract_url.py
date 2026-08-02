"""URL에서 기사 추출하는 /api/extract-url 테스트.

서버가 사용자 지정 URL로 대신 요청을 나가는 기능이라 SSRF가 핵심
리스크다. _is_safe_public_host는 실제 소켓 조회(127.0.0.1 등 리터럴은
네트워크 없이 즉시 풀린다)로, 나머지는 requests.get을 패치해 실제
네트워크 호출 없이 검증한다.

patch 대상은 routes.extract_url이다 — 이 라우트가 직접 호출하는
이름들(require_user_id, _is_safe_public_host, requests.get)은 전부 이
모듈의 네임스페이스에서 찾아지므로, main.X를 patch해도 적용되지 않는다.
"""
import pytest
import httpx
import requests
from unittest.mock import patch, MagicMock
from main import app
from routes.extract_url import _is_safe_public_host, MAX_URL_FETCH_BYTES


class FakeResponse:
    """requests.Response 흉내. status_code/headers/iter_content/close만 쓴다."""

    def __init__(self, status_code=200, headers=None, body=b"", location=None):
        self.status_code = status_code
        self.headers = headers or {}
        if location:
            self.headers["Location"] = location
        self._body = body
        self.closed = False

    def iter_content(self, chunk_size=65536):
        for i in range(0, len(self._body), chunk_size):
            yield self._body[i:i + chunk_size]

    def close(self):
        self.closed = True


ARTICLE_HTML = ("<html><head><title>테스트 기사 제목</title></head><body><article>"
                 + "<p>" + ("이것은 충분히 긴 기사 본문 문단입니다. " * 20) + "</p>"
                 + "</article></body></html>").encode("utf-8")


def _auth_headers():
    from auth import create_access_token
    token = create_access_token({"sub": "test_user_id"})
    return {"Authorization": f"Bearer {token}"}


# ---- _is_safe_public_host: 순수 함수, 실제 네트워크 없이 검증 ----

def test_is_safe_public_host_blocks_private_ranges():
    assert _is_safe_public_host("127.0.0.1") is False
    assert _is_safe_public_host("10.0.0.5") is False
    assert _is_safe_public_host("192.168.1.1") is False
    assert _is_safe_public_host("169.254.169.254") is False  # 클라우드 메타데이터
    assert _is_safe_public_host("0.0.0.0") is False


def test_is_safe_public_host_allows_public_ip():
    # DNS 조회 없이 바로 IP 리터럴을 넣어 네트워크 호출 없이 검증한다.
    assert _is_safe_public_host("8.8.8.8") is True


def test_is_safe_public_host_rejects_unresolvable():
    assert _is_safe_public_host("this-domain-should-not-exist-xyz123.invalid") is False


# ---- /api/extract-url 엔드포인트 ----

@pytest.mark.asyncio
async def test_extract_url_requires_auth():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/extract-url", json={"url": "https://example.com"})
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_extract_url_rejects_private_ip():
    with patch("routes.extract_url.require_user_id", return_value="test_user_id"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/extract-url", json={"url": "http://127.0.0.1/secret"}, headers=_auth_headers()
            )
            assert response.status_code == 400
            assert "내부망" in response.json()["detail"]


@pytest.mark.asyncio
async def test_extract_url_rejects_non_http_scheme():
    with patch("routes.extract_url.require_user_id", return_value="test_user_id"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/extract-url", json={"url": "file:///etc/passwd"}, headers=_auth_headers()
            )
            assert response.status_code == 400


@pytest.mark.asyncio
async def test_extract_url_success():
    fake = FakeResponse(status_code=200, headers={"Content-Type": "text/html; charset=utf-8"}, body=ARTICLE_HTML)
    with patch("routes.extract_url.require_user_id", return_value="test_user_id"), \
         patch("routes.extract_url._is_safe_public_host", return_value=True), \
         patch("routes.extract_url.requests.get", return_value=fake):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/extract-url", json={"url": "https://news.example.com/article/1"}, headers=_auth_headers()
            )
            assert response.status_code == 200
            data = response.json()
            assert data["filename"] == "테스트 기사 제목"
            assert data["char_count"] > 200
            assert "충분히 긴 기사 본문" in data["preview"]
            assert fake.closed is True


@pytest.mark.asyncio
async def test_extract_url_follows_safe_redirect():
    redirect = FakeResponse(status_code=302, location="https://final.example.com/article")
    final = FakeResponse(status_code=200, headers={"Content-Type": "text/html"}, body=ARTICLE_HTML)
    with patch("routes.extract_url.require_user_id", return_value="test_user_id"), \
         patch("routes.extract_url._is_safe_public_host", return_value=True), \
         patch("routes.extract_url.requests.get", side_effect=[redirect, final]):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/extract-url", json={"url": "https://short.example.com/x"}, headers=_auth_headers()
            )
            assert response.status_code == 200


@pytest.mark.asyncio
async def test_extract_url_blocks_redirect_to_private_ip():
    # 첫 응답은 공인 IP에서 오는 정상 302처럼 보이지만, 목적지가 내부망이다.
    # 최종 목적지만 보면 놓치는 공격 패턴이라, 매 홉을 다시 검증해야 잡힌다.
    redirect = FakeResponse(status_code=302, location="http://127.0.0.1/admin")
    with patch("routes.extract_url.require_user_id", return_value="test_user_id"), \
         patch("routes.extract_url.requests.get", return_value=redirect):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/extract-url", json={"url": "https://safe.example.com/x"}, headers=_auth_headers()
            )
            assert response.status_code == 400
            assert "내부망" in response.json()["detail"]


@pytest.mark.asyncio
async def test_extract_url_rejects_non_html_content_type():
    fake = FakeResponse(status_code=200, headers={"Content-Type": "application/pdf"}, body=b"%PDF-1.4")
    with patch("routes.extract_url.require_user_id", return_value="test_user_id"), \
         patch("routes.extract_url._is_safe_public_host", return_value=True), \
         patch("routes.extract_url.requests.get", return_value=fake):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/extract-url", json={"url": "https://example.com/file.pdf"}, headers=_auth_headers()
            )
            assert response.status_code == 400
            assert "HTML" in response.json()["detail"]


@pytest.mark.asyncio
async def test_extract_url_rejects_oversized_page():
    huge_body = b"x" * (MAX_URL_FETCH_BYTES + 1024)
    fake = FakeResponse(status_code=200, headers={"Content-Type": "text/html"}, body=huge_body)
    with patch("routes.extract_url.require_user_id", return_value="test_user_id"), \
         patch("routes.extract_url._is_safe_public_host", return_value=True), \
         patch("routes.extract_url.requests.get", return_value=fake):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/extract-url", json={"url": "https://example.com/huge"}, headers=_auth_headers()
            )
            assert response.status_code == 413


@pytest.mark.asyncio
async def test_extract_url_rejects_js_rendered_page():
    # 본문이 없는(자바스크립트로 나중에 채워지는) 페이지: 추출 결과가
    # 너무 짧으면 조용히 빈 오디오를 만드는 대신 명확히 에러를 준다.
    thin_html = b"<html><body><div id='app'></div><script>renderApp()</script></body></html>"
    fake = FakeResponse(status_code=200, headers={"Content-Type": "text/html"}, body=thin_html)
    with patch("routes.extract_url.require_user_id", return_value="test_user_id"), \
         patch("routes.extract_url._is_safe_public_host", return_value=True), \
         patch("routes.extract_url.requests.get", return_value=fake):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/extract-url", json={"url": "https://spa.example.com/"}, headers=_auth_headers()
            )
            assert response.status_code == 422
            assert "자바스크립트" in response.json()["detail"]


@pytest.mark.asyncio
async def test_extract_url_reports_a_korean_message_when_the_site_times_out():
    with patch("routes.extract_url.require_user_id", return_value="test_user_id"), \
         patch("routes.extract_url._is_safe_public_host", return_value=True), \
         patch("routes.extract_url.requests.get", side_effect=requests.ConnectTimeout):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/extract-url", json={"url": "https://m.yonhapnews.co.kr/news/article"}, headers=_auth_headers()
            )

    assert response.status_code == 504
    assert "제한 시간" in response.json()["detail"]


@pytest.mark.asyncio
async def test_extract_url_missing_url_field():
    with patch("routes.extract_url.require_user_id", return_value="test_user_id"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/extract-url", json={}, headers=_auth_headers())
            assert response.status_code == 400
