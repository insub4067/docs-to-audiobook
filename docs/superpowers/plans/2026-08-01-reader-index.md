# 읽기 모드 자동 목차 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기존 허용 파일에서 명확한 제목을 인식해 읽기 모드의 기존 목차로 이동할 수 있게 한다.

**Architecture:** `main.py`의 추출 텍스트를 변형하지 않고, 기존 `extract_markdown_headings`가 Markdown 제목과 명확한 장·번호 제목을 모두 목차 메타데이터로 읽게 확장한다. 기존 문장 주석 처리와 읽기 모드 UI는 생성된 메타데이터를 그대로 사용한다.

**Tech Stack:** Python 3.14, FastAPI, pytest, 기존 Vanilla JavaScript 읽기 모드

## Global Constraints

- 지원 파일 형식은 기존 DOCX, PDF, TXT, MD, HWP로 한정한다.
- 제목이 없는 문서는 목차를 만들지 않는다.
- 일반 문단이나 짧은 행을 제목으로 추측하지 않는다.
- 기존 Markdown 제목 인식과 읽기 모드 목차 UI를 유지한다.
- 사용자에게 보이는 새 문구나 새 UI는 추가하지 않는다.

---

### Task 1: 번호 제목 인식 확장

**Files:**
- Modify: `main.py:348-371`
- Test: `tests/test_text_processing.py`

**Interfaces:**
- Consumes: `extract_markdown_headings(raw_text: str) -> list`
- Produces: `{cleaned_text: str, display_text: str, level: int}` 항목의 기존 목차 메타데이터

- [x] **Step 1: Write the failing test**

```python
def test_extract_markdown_headings_includes_clear_chapter_lines():
    raw_text = (
        "데미안 (Demian) - 제1장 두 세계 (Chapter 1: Two Worlds)\n"
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
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_text_processing.py::test_extract_markdown_headings_includes_clear_chapter_lines -v`

Expected: FAIL because plain chapter and numbered lines are not currently returned.

- [x] **Step 3: Write minimal implementation**

```python
chapter_heading_pattern = re.compile(r"(?:^|\s)(?:제\s*\d+\s*(?:장|부|절)|\d+(?:\.\d+)*\.)\s*\S+")

if markdown_match:
    level = len(markdown_match.group(1))
    display = re.sub(r"[*_~`\\]", "", markdown_match.group(2)).strip()
elif chapter_heading_pattern.search(stripped):
    level = 1
    display = stripped
else:
    continue
```

Keep the existing `clean_tts_text` conversion and result object shape unchanged.

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_text_processing.py::test_extract_markdown_headings_includes_clear_chapter_lines -v`

Expected: PASS

- [x] **Step 5: Commit**

```bash
git add main.py tests/test_text_processing.py
git commit -m "feat: 장 제목을 읽기 목차에 반영"
```

### Task 2: 최종 확인

**Files:**
- Modify: 없음

**Interfaces:**
- Consumes: 제목 인식과 문장 전처리 결과
- Produces: 읽기 모드가 소비하는 기존 목차 메타데이터

- [x] **Step 1: Run final verification**

Run: `node --check static/app.js && pytest -q && git diff --check`

Expected: PASS with no whitespace errors.

- [x] **Step 2: Commit and push**

```bash
git add main.py tests/test_text_processing.py
git commit -m "feat: 장 제목을 읽기 목차에 반영"
git push origin main
```

## Self-review

- Spec coverage: 제목 인식, 제목 없는 문서 처리, 기존 읽기 모드 재사용, 지원 형식 제한을 Task 1~2에 반영했다.
- Placeholder scan: 미결정 항목과 추상적 오류 처리 지시가 없다.
- Type consistency: 기존 `extract_markdown_headings` 반환 형식과 `annotate_sentences_with_headings` 소비 형식을 유지한다.
