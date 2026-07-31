import pytest
from main import clean_tts_text, extract_markdown_headings, preprocess_text

def test_clean_tts_text():
    # Headers
    assert clean_tts_text("### Chapter 1") == "Chapter 1"
    
    # Bold, Italic, Strikethrough
    assert clean_tts_text("**Hello** _world_ ~test~") == "Hello world test"
    
    # Blockquotes
    assert clean_tts_text("> A quote") == "A quote"
    
    # Parentheses cleanup (e.g. "한글 (English)")
    assert clean_tts_text("사과 (Apple)") == "사과"
    assert clean_tts_text("홍길동 (Hong Gil Dong)") == "홍길동"
    assert clean_tts_text("1 (One)") == "1"
    
    # Keep normal parentheses
    assert clean_tts_text("이것은 (테스트) 입니다") == "이것은 (테스트) 입니다"
    
    # Multiple spaces
    assert clean_tts_text("  Too   many    spaces  ") == "Too many spaces"

def test_extract_markdown_headings():
    raw_text = """
# Title
Some text here.
## Subtitle 1
More text.
### Subtitle 2
Final text.
"""
    headings = extract_markdown_headings(raw_text)
    assert len(headings) == 3
    
    assert headings[0]["display_text"] == "Title"
    assert headings[0]["cleaned_text"] == "Title"
    
    assert headings[1]["display_text"] == "Subtitle 1"
    assert headings[1]["cleaned_text"] == "Subtitle 1"
    
    assert headings[2]["display_text"] == "Subtitle 2"
    assert headings[2]["cleaned_text"] == "Subtitle 2"

def test_preprocess_text():
    raw_text = """
    This is a test.  
    
    It has newlines.
    
    And *markdown* formatting!
    """
    processed = preprocess_text(raw_text)
    assert "This is a test." in processed
    assert "It has newlines." in processed
    assert "And *markdown* formatting!" in processed
    assert "\n\n" not in processed # preprocess_text shouldn't have excessive newlines if it normalizes them
