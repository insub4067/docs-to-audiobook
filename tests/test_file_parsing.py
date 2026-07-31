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
