from text_processing import clean_tts_text, extract_markdown_headings, preprocess_text

def test_clean_tts_text():
    # Headers
    assert clean_tts_text("### Chapter 1") == "Chapter 1"
    
    # Bold, Italic, Strikethrough
    assert clean_tts_text("**Hello** _world_ ~test~") == "Hello world test"
    
    # Blockquotes
    assert clean_tts_text("> A quote") == "A quote"
    
    # 괄호 안 내용은 언어와 무관하게 낭독하지 않는다
    assert clean_tts_text("사과 (Apple)") == "사과"
    assert clean_tts_text("홍길동 (Hong Gil Dong)") == "홍길동"
    assert clean_tts_text("1 (One)") == "1"
    assert clean_tts_text("이것은 (테스트) 입니다") == "이것은 입니다"
    
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


def test_extract_markdown_headings_includes_clear_chapter_lines():
    raw_text = (
        "\ufeff데미안 (Demian) - 제1장 두 세계 (Chapter 1: Two Worlds)\n"
        "첫 문단입니다.\n"
        "2. 다음 장\n"
        "둘째 문단입니다."
    )

    headings = extract_markdown_headings(raw_text)

    assert [(item["display_text"], item["level"]) for item in headings] == [
        ("데미안 (Demian) - 제1장 두 세계 (Chapter 1: Two Worlds)", 1),
        ("2. 다음 장", 1),
    ]
    assert extract_markdown_headings("나는 열 살 무렵 이야기를 시작하려 한다.\n짧은 행") == []


def test_preprocess_text_keeps_clear_chapter_lines_separate_from_body():
    text = preprocess_text("제1장 두 세계\n첫 문단입니다.")

    assert text == "제1장 두 세계. 첫 문단입니다."

def test_clean_tts_text_edge_cases():
    # Emojis and special characters
    assert clean_tts_text("Hello 😊 world! 🚀") == "Hello 😊 world! 🚀"
    assert clean_tts_text("테스트 🍎 123 ㅋㅋㅋ") == "테스트 🍎 123 ㅋㅋㅋ"
    
    # Markdown links and images: 괄호 안(URL)은 제거되고 대괄호 표기만 남는다
    assert clean_tts_text("Click [here](http://example.com) for info.") == "Click [here] for info."
    assert clean_tts_text("Image ![alt](img.jpg)") == "Image ![alt]"

    # 중첩된 괄호도 안쪽부터 전부 제거된다
    assert clean_tts_text("이것은 (테스트(중첩)) 입니다") == "이것은 입니다"
    assert clean_tts_text("안녕 (Hello) 세상 (World)") == "안녕 세상"
    
    # Markdown tables (should ideally be stripped or handled gracefully)
    assert clean_tts_text("| Header 1 | Header 2 |") == "| Header 1 | Header 2 |"
    
    # Empty or whitespace only
    assert clean_tts_text("") == ""
    assert clean_tts_text("   \n\t  ") == ""
    
    # Code blocks (inline)
    assert clean_tts_text("Use `code` here") == "Use code here"

def test_extract_markdown_headings_edge_cases():
    raw_text = """
Some text
# Heading 1
More text
    ## Indented Heading 2
Text
#Heading without space
#  Heading with double space
Not a # heading in middle
```python
# Not a heading, it's a comment
def foo(): pass
```
"""
    headings = extract_markdown_headings(raw_text)
    
    # Check valid headings
    titles = [h["display_text"] for h in headings]
    assert "Heading 1" in titles
    
    # Let's just do a clean test
    raw_text_2 = "# Valid1\n## Valid2\n### Valid3\n#### Invalid4 (level 4)"
    h2 = extract_markdown_headings(raw_text_2)
    assert len(h2) == 3
    assert h2[0]["level"] == 1
    assert h2[1]["level"] == 2
    assert h2[2]["level"] == 3

from text_processing import annotate_sentences_with_headings
def test_annotate_sentences_with_headings():
    sentences = [
        {"text": "Title here", "start": 0}, 
        {"text": "Some content", "start": 10}, 
        {"text": "Subtitle here", "start": 20}, 
        {"text": "More content", "start": 30}
    ]
    headings = [
        {"cleaned_text": "Title here", "display_text": "Title here", "level": 1},
        {"cleaned_text": "Subtitle here", "display_text": "Subtitle here", "level": 2}
    ]
    
    annotated, _ = annotate_sentences_with_headings(sentences, headings)
    assert len(annotated) == 4
    assert annotated[0].get("type") == "heading"
    assert annotated[0]["level"] == 1
    assert annotated[1].get("type") != "heading"
    assert annotated[2].get("type") == "heading"
    assert annotated[2]["level"] == 2
    assert annotated[3].get("type") != "heading"

def test_preprocess_text():
    raw_text = """
    This is a test.  
    
    It has newlines.
    
    And *markdown* formatting!
    """
    from text_processing import preprocess_text
    processed = preprocess_text(raw_text)
    assert "This is a test." in processed
    assert "It has newlines." in processed
    assert "And *markdown* formatting!" in processed
    assert "\n\n" not in processed
