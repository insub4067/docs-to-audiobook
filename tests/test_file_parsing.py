import pytest
from fastapi import HTTPException
from main import extract_text


def test_extract_text_txt(tmp_path):
    # UTF-8 / CP949 인코딩 자동 감지
    utf8_file = tmp_path / "test_utf8.txt"
    utf8_file.write_text("안녕 세계 UTF-8", encoding="utf-8")

    cp949_file = tmp_path / "test_cp949.txt"
    cp949_file.write_text("안녕 세계 CP949", encoding="cp949")

    assert extract_text(str(utf8_file), "test_utf8.txt") == "안녕 세계 UTF-8"
    assert extract_text(str(cp949_file), "test_cp949.txt") == "안녕 세계 CP949"


def test_extract_text_unsupported(tmp_path):
    png_file = tmp_path / "test_image.png"
    png_file.write_bytes(b"fake png data")

    with pytest.raises(HTTPException) as exc_info:
        extract_text(str(png_file), png_file.name)
    assert exc_info.value.status_code == 400
    assert "지원하지 않는 파일 형식입니다" in exc_info.value.detail


def test_extract_text_empty_hwp(tmp_path):
    hwp_file = tmp_path / "test_broken.hwp"
    hwp_file.write_bytes(b"broken hwp")

    with pytest.raises(HTTPException) as exc_info:
        extract_text(str(hwp_file), hwp_file.name)
    assert exc_info.value.status_code == 400
    assert "HWP 파일 해석 실패" in exc_info.value.detail


def test_extract_text_docx(tmp_path):
    from unittest.mock import patch, MagicMock

    with patch("main.docx.Document") as mock_doc:
        mock_instance = MagicMock()
        mock_para = MagicMock()
        mock_para.text = "Hello Docx"
        mock_instance.paragraphs = [mock_para]
        mock_doc.return_value = mock_instance

        docx_file = tmp_path / "test.docx"
        docx_file.write_text("dummy")

        content = extract_text(str(docx_file), docx_file.name)
        assert content == "Hello Docx"


def test_extract_text_pdf(tmp_path):
    from unittest.mock import patch, MagicMock

    with patch("main.pypdf.PdfReader") as mock_pdf:
        mock_instance = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Hello PDF"
        mock_instance.pages = [mock_page]
        mock_pdf.return_value = mock_instance

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_text("dummy")

        content = extract_text(str(pdf_file), pdf_file.name)
        assert content == "Hello PDF"


def test_extract_text_valid_hwp(tmp_path, monkeypatch):
    from unittest.mock import MagicMock
    import sys

    mock_ole = MagicMock()
    mock_instance = MagicMock()
    mock_instance.listdir.return_value = [['FileHeader'], ['BodyText']]
    mock_header_stream = MagicMock()
    mock_header_stream.read.return_value = b'\x00' * 36 + b'\x00' + b'\x00' * 200
    mock_body_stream = MagicMock()
    mock_body_stream.read.return_value = b'\x43\x00\x40\x00A\x00B\x00'

    def openstream_mock(name):
        if name == 'FileHeader' or name == ['FileHeader']:
            return mock_header_stream
        if name == 'BodyText' or name == ['BodyText']:
            return mock_body_stream

    mock_instance.openstream = openstream_mock
    mock_ole.OleFileIO.return_value = mock_instance

    # sys.modules를 직접 건드리지 않고 monkeypatch로 등록한다.
    # 테스트가 실패하거나 예외로 중간에 빠져도 다른 테스트에 영향이 없다
    # (기존 코드는 try/finally로 수동 정리했는데, 정리 로직 자체가
    # 빠지거나 순서가 꼬이면 olefile/zlib/struct가 이후 테스트에도 가짜로 남는다).
    monkeypatch.setitem(sys.modules, 'olefile', mock_ole)
    monkeypatch.setitem(sys.modules, 'zlib', MagicMock())
    mock_struct = MagicMock()
    monkeypatch.setitem(sys.modules, 'struct', mock_struct)
    mock_struct.unpack.side_effect = [(4194371,), (4,)]  # (header_val), (rec_len)

    hwp_file = tmp_path / "test_valid.hwp"
    hwp_file.write_text("dummy")

    content = extract_text(str(hwp_file), hwp_file.name)
    assert "AB" in content
