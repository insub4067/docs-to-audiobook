"""순수 문서/텍스트 처리.

파일 파싱(HWP/PDF/DOCX/TXT)부터 마크다운·표 구조화, 문장·헤딩 주석까지.
FastAPI 라우트나 전역 상태에 의존하지 않는다(HTTPException은 파싱 실패를
알리는 값으로만 쓴다) — 그래서 이 모듈은 다른 어떤 라우트 모듈도 몰라도 된다.
"""
import os
import re
import docx
import pypdf
from collections import Counter
from fastapi import HTTPException


def extract_hwp_text(filepath: str) -> str:
    try:
        import olefile
        import zlib
        import struct

        f = olefile.OleFileIO(filepath)
        dirs = f.listdir()
        if ['FileHeader'] not in dirs:
            return ""
        header = f.openstream('FileHeader').read()
        is_compressed = (header[36] & 1) != 0

        sections = [d for d in dirs if d[0] == 'BodyText']
        text_chunks = []
        for sec in sections:
            stream = f.openstream(sec).read()
            if is_compressed:
                stream = zlib.decompress(stream, -15)
            
            i = 0
            while i < len(stream):
                if i + 4 > len(stream):
                    break
                header_val = struct.unpack('<I', stream[i:i+4])[0]
                rec_type = header_val & 0x3FF
                rec_len = (header_val >> 20) & 0xFFF
                if rec_len == 0xFFF:
                    if i + 8 > len(stream):
                        break
                    rec_len = struct.unpack('<I', stream[i+4:i+8])[0]
                    i += 8
                else:
                    i += 4
                
                if rec_type == 67:  # HWPTAG_PARA_TEXT
                    data = stream[i:i+rec_len]
                    text = data.decode('utf-16le', errors='ignore')
                    # Remove HWP control characters / inline objects
                    clean_chars = [c for c in text if ord(c) >= 32 or c in ('\n', '\r', '\t')]
                    text_chunks.append("".join(clean_chars))
                i += rec_len
        return "\n".join(text_chunks)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"HWP 파일 해석 실패: {str(e)}")

def _looks_like_garbled_pdf_extraction(text: str) -> bool:
    """서브셋 폰트에 ToUnicode CMap이 없는 PDF는 서로 다른 글리프가 전부
    같은 엉뚱한 문자로 매핑돼, 정상 텍스트라면 나올 수 없는 비율로 특정
    한 글자가 반복된다("PART G Chapter GG G G GG..." 형태). 완벽히 고칠
    방법이 마땅치 않은 pypdf/PDF 자체의 한계라, 조용히 진행해 몇 시간
    분량을 엉터리로 합성하는 대신 여기서 걸러 명확히 알린다."""
    stripped = re.sub(r"\s", "", text)
    if len(stripped) < 200:
        return False
    most_common_char, most_common_count = Counter(stripped).most_common(1)[0]
    return (most_common_count / len(stripped)) > 0.15

def extract_text(file_path: str, filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".docx":
        doc = docx.Document(file_path)
        return "\n".join([para.text for para in doc.paragraphs])
    elif ext == ".pdf":
        reader = pypdf.PdfReader(file_path)
        text_list = []
        for page in reader.pages:
            t = page.extract_text(extraction_mode="layout")
            if t:
                text_list.append(t)
        result = normalize_pdf_for_reading("\n".join(text_list))
        if _looks_like_garbled_pdf_extraction(result):
            raise HTTPException(
                status_code=400,
                detail="이 PDF에서 텍스트를 정상적으로 추출하지 못했습니다. "
                       "폰트가 특수하게 인코딩된 PDF일 수 있습니다. DOCX나 TXT로 다시 시도해 주세요.",
            )
        return result
    elif ext in [".txt", ".md", ".markdown"]:
        for encoding in ["utf-8", "cp949", "euc-kr", "utf-16", "latin-1"]:
            try:
                with open(file_path, "r", encoding=encoding) as f:
                    content = f.read()
                    return content
            except UnicodeDecodeError:
                continue
        raise HTTPException(status_code=400, detail="텍스트 파일 인코딩을 분석할 수 없습니다. UTF-8로 변환해 주세요.")
    elif ext == ".hwp":
        text = extract_hwp_text(file_path)
        if not text.strip():
            raise HTTPException(status_code=400, detail="HWP 파일에서 텍스트를 추출할 수 없습니다.")
        return text
    else:
        raise HTTPException(status_code=400, detail="지원하지 않는 파일 형식입니다. (지원: .docx, .pdf, .txt, .md, .hwp)")

def parse_heading_line(line: str) -> tuple[int, str] | None:
    stripped = line.strip().lstrip("\ufeff")
    markdown_match = re.match(r'^(#{1,3})\s+(.+)$', stripped)
    if markdown_match:
        return len(markdown_match.group(1)), re.sub(r'[*_~`\\]', '', markdown_match.group(2)).strip()
    if re.search(r'(?:^|[\s\-—:])제\s*\d+\s*(?:장|부|절)(?=\s|$)', stripped):
        return 1, stripped
    if re.match(r'^\d+(?:\.\d+)*[.)]\s+\S', stripped):
        return 1, stripped
    return None

def _pdf_layout_cells(line: str) -> list[str]:
    return [cell.strip() for cell in re.split(r"\s{2,}", line.strip()) if cell.strip()]

def normalize_pdf_for_reading(text: str) -> str:
    """PDF 레이아웃 텍스트를 리더용 Markdown 구조로 정리한다."""
    lines = text.split("\n")
    normalized = []
    index = 0

    while index < len(lines):
        line = lines[index].strip()
        cells = _pdf_layout_cells(line)

        if len(cells) >= 2:
            rows = [cells]
            next_index = index + 1
            while next_index < len(lines):
                next_cells = _pdf_layout_cells(lines[next_index])
                if len(next_cells) != len(cells):
                    break
                rows.append(next_cells)
                next_index += 1

            if len(rows) >= 2:
                normalized.append("| " + " | ".join(rows[0]) + " |")
                normalized.append("| " + " | ".join("---" for _ in rows[0]) + " |")
                normalized.extend("| " + " | ".join(row) + " |" for row in rows[1:])
                index = next_index
                continue

        heading = parse_heading_line(line)
        if heading:
            level, display = heading
            normalized.append("#" * level + " " + display)
        elif re.match(r"^[•◦▪]\s+", line):
            normalized.append("- " + re.sub(r"^[•◦▪]\s+", "", line))
        else:
            normalized.append(line)
        index += 1

    return "\n".join(normalized)

def _markdown_table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]

def _is_markdown_table_separator(line: str) -> bool:
    cells = _markdown_table_cells(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)

def normalize_markdown_for_reading(text: str) -> str:
    """표와 문법 기호를 TTS·리더에서 자연스러운 문장으로 바꾼다."""
    lines = re.sub(r"<br\s*/?>", ". ", text, flags=re.IGNORECASE).split("\n")
    normalized = []
    index = 0

    while index < len(lines):
        line = lines[index]
        if (
            "|" in line
            and index + 1 < len(lines)
            and _is_markdown_table_separator(lines[index + 1])
        ):
            headers = _markdown_table_cells(line)
            index += 2
            while index < len(lines) and "|" in lines[index]:
                values = _markdown_table_cells(lines[index])
                pairs = [
                    f"{header or '항목'}: {value}"
                    for header, value in zip(headers, values)
                    if value
                ]
                if pairs:
                    normalized.append(". ".join(pairs) + ".")
                index += 1
            continue

        if re.fullmatch(r"\s*(?:[-*_]\s*){3,}", line):
            index += 1
            continue

        normalized.append(re.sub(r"^\s*>\s?", "", line))
        index += 1

    return "\n".join(normalized)

def extract_markdown_tables(text: str) -> list:
    tables = []
    lines = text.split("\n")
    index = 0
    while index + 1 < len(lines):
        if "|" not in lines[index] or not _is_markdown_table_separator(lines[index + 1]):
            index += 1
            continue
        headers = _markdown_table_cells(lines[index])
        rows = []
        index += 2
        while index < len(lines) and "|" in lines[index]:
            values = _markdown_table_cells(lines[index])
            if len(values) == len(headers):
                rows.append(values)
            index += 1
        if headers and rows:
            tables.append({"headers": headers, "rows": rows})
    return tables

def build_document_representations(raw_text: str) -> tuple[str, str, list]:
    """표 구조를 보존한 표시용 Markdown과 낭독용 평탄 텍스트를 분리한다."""
    display_markdown = raw_text.lstrip("\ufeff").replace("\r\n", "\n")
    return display_markdown, preprocess_text(display_markdown), extract_markdown_tables(display_markdown)

def _normalized_match_text(text: str) -> str:
    return re.sub(r"[^\w가-힣]", "", clean_tts_text(text))

def annotate_sentences_with_tables(sentences: list, tables: list) -> None:
    """TTS 문장에 표시용 표의 행·열 정보를 붙인다. 완전 매칭된 표만 표시한다."""
    search_start = 0
    for table_id, table in enumerate(tables):
        table_start = search_start
        matches = []
        for row_index, row in enumerate(table["rows"]):
            for column_index, value in enumerate(row):
                expected = _normalized_match_text(f"{table['headers'][column_index]}: {value}")
                found = None
                for sentence_index in range(search_start, len(sentences)):
                    actual = _normalized_match_text(sentences[sentence_index]["text"])
                    if expected and (actual == expected or expected in actual):
                        found = sentence_index
                        break
                if found is None:
                    matches = []
                    break
                matches.append((found, row_index, column_index))
                search_start = found + 1
            if not matches:
                break
        if not matches:
            search_start = table_start
            continue
        for sentence_index, row_index, column_index in matches:
            sentences[sentence_index]["table"] = {
                "id": table_id,
                "row": row_index,
                "column": column_index,
                "header": table["headers"][column_index],
            }

def preprocess_text(text: str) -> str:
    # 1. Clean line breaks: single newline to space, double newline to paragraph break with pause indicator
    cleaned_text = normalize_markdown_for_reading(
        text.lstrip("\ufeff").replace("\r\n", "\n")
    )
    
    # 2. Prevent headings from merging with the next paragraph
    lines = cleaned_text.split('\n')
    for i in range(len(lines)):
        line = lines[i].strip()
        # 제목을 별도 문장으로 유지해 다음 본문이 제목 처리되는 것을 막는다.
        if parse_heading_line(line) and not line.endswith('.'):
            lines[i] = line + "."
    cleaned_text = '\n'.join(lines)

    cleaned_text = cleaned_text.replace("\n\n", ".   ")
    cleaned_text = cleaned_text.replace("\n", " ")
    
    # 3. Clean consecutive spaces
    while "  " in cleaned_text:
        cleaned_text = cleaned_text.replace("  ", " ")
    cleaned_text = re.sub(r"([.!?])\s*\.", r"\1", cleaned_text)

    return cleaned_text.strip()

def extract_markdown_headings(raw_text: str) -> list:
    """Parse markdown headings from original text before TTS cleaning.
    Returns a list of {cleaned_text, level, display_text} dicts.
    """
    headings = []
    for line in raw_text.split('\n'):
        stripped = line.strip()
        if not stripped:
            continue

        heading = parse_heading_line(stripped)
        if not heading:
            continue

        level, display = heading

        cleaned = clean_tts_text(display)
        if cleaned:
            headings.append({
                "cleaned_text": cleaned,
                "display_text": display,
                "level": level
            })
    return headings

def annotate_sentences_with_headings(sentences: list, headings: list) -> tuple:
    """Match TTS sentences to extracted headings and annotate them.
    Returns (annotated_sentences, matched_headings_for_index).
    """
    heading_index = []
    remaining_headings = list(headings)  # copy so we can consume matches

    for i, s in enumerate(sentences):
        s_text = s["text"].strip()
        matched = False

        # Only check the next 3 headings to maintain order and allow for at most 2 skipped headings
        for h in remaining_headings[:3]:
            h_text = h["cleaned_text"].strip()
            
            # Remove all punctuation and spaces for a super robust match.
            # This handles cases where TTS splits "1. Title" into "1" and "Title".
            s_super_clean = re.sub(r'[^\w가-힣]', '', s_text)
            h_super_clean = re.sub(r'[^\w가-힣]', '', h_text)

            is_match = False
            if s_super_clean == h_super_clean:
                is_match = True
            elif h_super_clean in s_super_clean:
                is_match = True
            elif s_super_clean in h_super_clean and len(s_super_clean) >= len(h_super_clean) * 0.5:
                # If s_text is a substring of the heading, it must be at least half its length 
                # to prevent short random words/punctuation from stealing the heading.
                is_match = True

            if is_match:
                s["type"] = "heading"
                s["level"] = h["level"]
                s["display"] = h["display_text"]
                heading_index.append({
                    "text": h["display_text"],
                    "level": h["level"],
                    "sentIndex": i,
                    "startMs": s["start"]
                })
                remaining_headings.remove(h)
                matched = True
                break

        if not matched:
            s["type"] = "text"

    return sentences, heading_index

def clean_tts_text(text: str) -> str:
    # 1. 마크다운 특수문자 제거 (#, *, _, ~, `, \, > 등)
    t = re.sub(r'#+\s*', '', text)
    t = re.sub(r'[*_~`\\]', '', t)
    t = re.sub(r'>\s*', '', t)
    
    # 2. 한글 뒤 괄호 안의 영문(원문 표기) 제거: 예) 스캔들(A Scandal in Bohemia) -> 스캔들
    # 한글 문자나 숫자 바로 뒤에 오는 (영어/공백/문장부호) 괄호 패턴 제거
    t = re.sub(r'([가-힣0-9])\s*\([A-Za-z0-9\s.,\-\'\"]+\)', r'\1', t)
    
    # 3. 연속 공백 정리
    t = re.sub(r'\s+', ' ', t).strip()
    return t
