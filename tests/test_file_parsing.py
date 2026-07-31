import pytest
import os
from fastapi import HTTPException
from main import extract_text

def test_extract_text_txt():
    # Test UTF-8 and CP949 parsing
    test_file_utf8 = "test_utf8.txt"
    test_file_cp949 = "test_cp949.txt"
    
    with open(test_file_utf8, "w", encoding="utf-8") as f:
        f.write("안녕 세계 UTF-8")
        
    with open(test_file_cp949, "w", encoding="cp949") as f:
        f.write("안녕 세계 CP949")
        
    try:
        content_utf8 = extract_text(test_file_utf8, "test_utf8.txt")
        assert content_utf8 == "안녕 세계 UTF-8"
        
        content_cp949 = extract_text(test_file_cp949, "test_cp949.txt")
        assert content_cp949 == "안녕 세계 CP949"
    finally:
        if os.path.exists(test_file_utf8):
            os.remove(test_file_utf8)
        if os.path.exists(test_file_cp949):
            os.remove(test_file_cp949)

def test_extract_text_unsupported():
    test_file_png = "test_image.png"
    with open(test_file_png, "wb") as f:
        f.write(b"fake png data")
        
    try:
        with pytest.raises(HTTPException) as exc_info:
            extract_text(test_file_png, test_file_png)
        assert exc_info.value.status_code == 400
        assert "지원하지 않는 파일 형식입니다" in exc_info.value.detail
    finally:
        if os.path.exists(test_file_png):
            os.remove(test_file_png)

def test_extract_text_empty_hwp():
    # We simulate a broken/empty HWP file being parsed
    test_file_hwp = "test_broken.hwp"
    with open(test_file_hwp, "wb") as f:
        f.write(b"broken hwp")
        
    try:
        with pytest.raises(HTTPException) as exc_info:
            extract_text(test_file_hwp, test_file_hwp)
        assert exc_info.value.status_code == 400
        assert "HWP 파일 해석 실패" in exc_info.value.detail
    finally:
        if os.path.exists(test_file_hwp):
            os.remove(test_file_hwp)

def test_extract_text_docx():
    from unittest.mock import patch, MagicMock
    with patch("main.docx.Document") as mock_doc:
        mock_instance = MagicMock()
        mock_para = MagicMock()
        mock_para.text = "Hello Docx"
        mock_instance.paragraphs = [mock_para]
        mock_doc.return_value = mock_instance
        
        test_file = "test.docx"
        with open(test_file, "w") as f: f.write("dummy")
        try:
            content = extract_text(test_file, test_file)
            assert content == "Hello Docx"
        finally:
            os.remove(test_file)

def test_extract_text_pdf():
    from unittest.mock import patch, MagicMock
    with patch("main.pypdf.PdfReader") as mock_pdf:
        mock_instance = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Hello PDF"
        mock_instance.pages = [mock_page]
        mock_pdf.return_value = mock_instance
        
        test_file = "test.pdf"
        with open(test_file, "w") as f: f.write("dummy")
        try:
            content = extract_text(test_file, test_file)
            assert content == "Hello PDF"
        finally:
            os.remove(test_file)

def test_extract_text_valid_hwp():
    from unittest.mock import MagicMock
    import sys
    
    # Global patch of the olefile module
    mock_ole = MagicMock()
    mock_instance = MagicMock()
    mock_instance.listdir.return_value = [['FileHeader'], ['BodyText']]
    # Mock FileHeader to be uncompressed
    mock_header_stream = MagicMock()
    mock_header_stream.read.return_value = b'\x00' * 36 + b'\x00' + b'\x00' * 200
    # Mock BodyText
    mock_body_stream = MagicMock()
    mock_body_stream.read.return_value = b'\x43\x00\x40\x00A\x00B\x00'
    
    def openstream_mock(name):
        if name == 'FileHeader' or name == ['FileHeader']: return mock_header_stream
        if name == 'BodyText' or name == ['BodyText']: return mock_body_stream
    mock_instance.openstream = openstream_mock
    mock_ole.OleFileIO.return_value = mock_instance
    
    sys.modules['olefile'] = mock_ole
    sys.modules['zlib'] = MagicMock()
    sys.modules['struct'] = MagicMock()
    
    try:
        import struct
        struct.unpack.side_effect = [(4194371,), (4,)] # (header_val), (rec_len inside if)
        test_file = "test_valid.hwp"
        with open(test_file, "w") as f: f.write("dummy")
        content = extract_text(test_file, test_file)
        assert "AB" in content
    finally:
        if os.path.exists("test_valid.hwp"):
            os.remove("test_valid.hwp")
        # cleanup
        sys.modules.pop('olefile', None)
        sys.modules.pop('zlib', None)
        sys.modules.pop('struct', None)
