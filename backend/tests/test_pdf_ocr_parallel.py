"""고성능 PDF의 페이지 병렬 OCR 테스트.

예전에는 페이지를 한 장씩 차례로 돌렸다. 페이지마다 300dpi 렌더링과 Vision
왕복이 직렬로 붙어, 30쪽 문서가 30번의 왕복을 순서대로 기다렸다. 사용자가
"PDF가 너무 안 올라간다"고 한 게 이것이다.

여기서 지켜야 할 불변조건은 셋이다.
1. 동시에 보낸다 (한 장씩 기다리지 않는다).
2. 그래도 페이지 순서는 그대로다.
3. 몇 페이지까지 왔는지 밖에서 물어볼 수 있다.
"""
import asyncio
import sys
import threading
from unittest.mock import patch

import httpx
import pytest

from main import app
from routes import scan_text
from state import scan_progress


class _FakePixmap:
    def __init__(self, index: int):
        self.index = index

    def tobytes(self, _fmt: str) -> bytes:
        return f"png-{self.index}".encode()


class _FakePage:
    def __init__(self, index: int):
        self.index = index

    def get_pixmap(self, dpi: int):
        assert dpi == scan_text.PDF_OCR_RENDER_DPI
        return _FakePixmap(self.index)


class _FakeDoc:
    def __init__(self, pages: int):
        self.page_count = pages
        self.closed = False

    def __getitem__(self, index: int) -> _FakePage:
        return _FakePage(index)

    def close(self) -> None:
        self.closed = True


class _FakeFitz:
    def __init__(self, pages: int):
        self.doc = _FakeDoc(pages)

    def open(self, _path: str) -> _FakeDoc:
        return self.doc


def _with_fake_pdf(pages: int):
    """fitz는 함수 안에서 import하므로 sys.modules를 갈아끼우면 잡힌다."""
    return patch.dict(sys.modules, {"fitz": _FakeFitz(pages)})


@pytest.mark.asyncio
async def test_pages_are_ocred_concurrently():
    """⚠️ 이 파일에서 제일 중요한 검사다. 한 장씩 기다리면 여기서만 걸린다."""
    peak = 0
    running = 0
    lock = threading.Lock()

    def slow_ocr(png: bytes) -> str:
        nonlocal peak, running
        with lock:
            running += 1
            peak = max(peak, running)
        # to_thread로 도는 동기 함수라 진짜 스레드에서 겹친다.
        import time
        time.sleep(0.05)
        with lock:
            running -= 1
        return png.decode()

    with _with_fake_pdf(5), patch("routes.scan_text._detect_document_text", side_effect=slow_ocr):
        await scan_text.detect_pdf_text_via_ocr("x.pdf")

    assert peak > 1, f"페이지가 겹쳐서 처리되지 않았다 (최대 동시 {peak}장)"
    assert peak <= scan_text.PDF_OCR_PAGE_CONCURRENCY


@pytest.mark.asyncio
async def test_page_order_survives_batching():
    """동시에 보내도 본문은 원래 페이지 순서로 이어져야 한다. 순서가 섞이면
    문장 타임스탬프와 목차가 통째로 어긋난다."""
    async def jittered(png: bytes) -> str:
        # 뒷 페이지가 먼저 끝나게 만들어, 완료 순서로 이어붙이면 깨지게 한다.
        index = int(png.decode().split("-")[1])
        await asyncio.sleep(0.02 * (5 - index % 5))
        return f"본문{index}"

    def sync_wrapper(png: bytes) -> str:
        return asyncio.run(jittered(png))

    with _with_fake_pdf(7), patch("routes.scan_text._detect_document_text", side_effect=sync_wrapper):
        text = await scan_text.detect_pdf_text_via_ocr("x.pdf")

    assert text == "\n\n".join(f"본문{i}" for i in range(7))


@pytest.mark.asyncio
async def test_empty_pages_are_dropped():
    """빈 페이지(그림만 있는 장)가 빈 줄만 남기지 않아야 한다."""
    def ocr(png: bytes) -> str:
        index = int(png.decode().split("-")[1])
        return "" if index % 2 else f"본문{index}"

    with _with_fake_pdf(4), patch("routes.scan_text._detect_document_text", side_effect=ocr):
        text = await scan_text.detect_pdf_text_via_ocr("x.pdf")

    assert text == "본문0\n\n본문2"


@pytest.mark.asyncio
async def test_progress_is_reported_per_batch():
    """묶음이 끝날 때마다 진행 상황을 알린다. 총 페이지 수는 첫 보고부터
    나와야 한다 — 그래야 화면이 '? / ?' 대신 '0 / 12'를 띄운다."""
    seen: list[tuple[int, int]] = []

    with _with_fake_pdf(12), patch("routes.scan_text._detect_document_text", side_effect=lambda png: "본문"):
        await scan_text.detect_pdf_text_via_ocr("x.pdf", on_progress=lambda done, total: seen.append((done, total)))

    assert seen[0] == (0, 12), "시작하자마자 총 페이지 수를 알려야 한다"
    assert seen[-1] == (12, 12)
    assert [done for done, _ in seen] == [0, 5, 10, 12]


@pytest.mark.asyncio
async def test_document_is_closed_even_on_failure():
    """Vision이 죽어도 PDF 핸들은 닫아야 한다. 안 닫으면 요청마다 새는데,
    1GB 머신에서는 금방 티가 난다."""
    fake = _FakeFitz(3)
    with patch.dict(sys.modules, {"fitz": fake}), \
         patch("routes.scan_text._detect_document_text", side_effect=RuntimeError("vision down")), \
         pytest.raises(RuntimeError):
        await scan_text.detect_pdf_text_via_ocr("x.pdf")

    assert fake.doc.closed


def _admin_headers():
    from auth import create_access_token
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin'})}"}


@pytest.mark.asyncio
async def test_scan_progress_endpoint_reports_pages():
    scan_progress["scan-1"] = {"done": 7, "total": 20}
    with patch("routes.scan_text.require_admin_user", return_value="admin"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/scan-progress/scan-1", headers=_admin_headers())

    assert response.json() == {"done": 7, "total": 20}
    del scan_progress["scan-1"]


@pytest.mark.asyncio
async def test_unknown_scan_id_is_not_an_error():
    """아직 첫 페이지를 그리기 전이거나 이미 끝난 경우다. 404로 실패시키면
    화면이 폴링을 멈추거나 오류를 띄운다 — 그저 아직 모를 뿐이다."""
    with patch("routes.scan_text.require_admin_user", return_value="admin"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/scan-progress/없는-id", headers=_admin_headers())

    assert response.status_code == 200
    assert response.json() == {"done": None, "total": None}
