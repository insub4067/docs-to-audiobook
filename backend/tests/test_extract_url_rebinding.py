"""DNS 재바인딩 방어.

검사한 주소와 실제로 연결하는 주소가 다르면 SSRF 검사는 의미가 없다.
공격자가 자기 도메인의 DNS를 쥐고 있으면, 첫 조회에는 공인 IP를 주고
두 번째 조회(실제 연결)에는 169.254.169.254를 줄 수 있다.
"""
import http.server
import socket
import threading

import pytest
import requests
from fastapi import HTTPException

from routes import extract_url as module


@pytest.fixture
def local_server():
    """실제로 연결이 어디로 갔는지 확인할 수 있는 서버."""
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = b"<html><body>ok</body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1]
    server.shutdown()


@pytest.fixture(autouse=True)
def clean_pins():
    module._clear_pinned_hosts()
    yield
    module._clear_pinned_hosts()


def _entry(ip: str, port=0):
    """getaddrinfo가 돌려주는 모양. 포트를 실제로 반영해야 한다 — 무시하면
    고정을 껐을 때 포트 0으로 붙어, 방어가 없어도 연결이 실패하는 것처럼
    보인다(변이 검사가 거짓으로 통과한다)."""
    return (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, port or 0))


def test_connection_uses_the_address_that_was_checked(monkeypatch, local_server):
    """조회할 때마다 다른 답을 주는 DNS를 흉내낸다.

    첫 답(127.0.0.2)에는 아무도 듣고 있지 않고, 둘째 답(127.0.0.1)에는
    로컬 서버가 떠 있다. 고정이 없으면 requests가 둘째 답으로 붙어 **요청이
    성공한다** — 그게 재바인딩이다. 고정이 있으면 검사에 쓴 첫 답으로만
    나가므로 연결이 거부된다.

    (두 주소 모두 루프백이라 분류 검사는 여기서 통과시킨다. 이 테스트가
    보는 것은 "검사한 주소로 연결하는가"이지 분류가 아니다 — 분류는
    test_internal_address_is_rejected_before_any_request가 본다.)
    """
    answers = iter(["127.0.0.2", "127.0.0.1"])

    def rebinding_dns(host, port=0, *args, **kwargs):
        if host == "evil.example":
            return [_entry(next(answers), port)]
        return module.socket.getaddrinfo(host, port, *args, **kwargs)

    monkeypatch.setattr(module, "_system_getaddrinfo", rebinding_dns)
    monkeypatch.setattr(module, "_is_public_address", lambda _address: True)
    monkeypatch.setattr(module, "URL_FETCH_TIMEOUT_SEC", 3)

    with pytest.raises(requests.RequestException):
        module._fetch_url_safely(f"http://evil.example:{local_server}/")


def test_internal_address_is_rejected_before_any_request(monkeypatch):
    monkeypatch.setattr(
        module, "_system_getaddrinfo",
        lambda *a, **k: [_entry("169.254.169.254")],
    )

    def must_not_be_called(*args, **kwargs):
        raise AssertionError("검사에서 걸러야 하고, 요청은 나가면 안 된다")

    monkeypatch.setattr(module.requests, "get", must_not_be_called)

    with pytest.raises(HTTPException) as exc:
        module._fetch_url_safely("http://metadata.example/")
    assert exc.value.status_code == 400


def test_public_host_still_works(monkeypatch, local_server):
    """방어가 정상 요청을 막으면 안 된다. 검사와 연결 모두 같은 주소를
    주는(=정상) DNS에서는 그대로 동작해야 한다."""
    monkeypatch.setattr(
        module, "_system_getaddrinfo",
        lambda host, port=0, *a, **k: [_entry("127.0.0.1", port)] if host == "good.example"
        else module.socket.getaddrinfo(host, port, *a, **k),
    )
    # 로컬 서버로 붙여야 검증이 가능하므로, 이 테스트에서만 루프백을 허용한다.
    monkeypatch.setattr(module, "_is_public_address", lambda _address: True)

    response = module._fetch_url_safely(f"http://good.example:{local_server}/")
    assert response.status_code == 200
    response.close()


def test_pins_do_not_leak_between_requests(monkeypatch, local_server):
    """스레드는 풀에서 재사용된다. 고정이 남으면 다음 요청이 낡은 주소로 나간다."""
    monkeypatch.setattr(
        module, "_system_getaddrinfo",
        lambda host, port=0, *a, **k: [_entry("127.0.0.1", port)],
    )
    monkeypatch.setattr(module, "_is_public_address", lambda _address: True)

    module._fetch_url_safely(f"http://good.example:{local_server}/").close()

    assert getattr(module._pinned, "by_host", {}) == {}
