import re

def clean_tts_text(text: str) -> str:
    t = re.sub(r'#+\s*', '', text)
    t = re.sub(r'[*_~`\\]', '', t)
    t = re.sub(r'>\s*', '', t)
    t = re.sub(r'([가-힣0-9])\s*\([A-Za-z0-9\s.,\-\'\"]+\)', r'\1', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t

def extract_markdown_headings(raw_text: str) -> list:
    headings = []
    for line in raw_text.split('\n'):
        stripped = line.strip()
        if not stripped: continue
        
        m = re.match(r'^(#{1,3})\s+(.+)$', stripped)
        if m:
            level = len(m.group(1))
            display = re.sub(r'[*_~`\\]', '', m.group(2)).strip()
            cleaned = clean_tts_text(m.group(2))
            if cleaned: headings.append({"cleaned_text": cleaned, "display_text": display, "level": level})
            continue

        m = re.match(r'^(\*\*|__)(.+?)\1$', stripped)
        if m and len(stripped) < 80:
            display = m.group(2).strip()
            cleaned = clean_tts_text(display)
            if cleaned: headings.append({"cleaned_text": cleaned, "display_text": display, "level": 2})
            continue

        m = re.match(r'^(\*\*|__)?((\d+[\.\s]+|[IVXLCDM]+\.\s+|[A-Z]\.\s+)(.+?))\1?$', stripped)
        if m and len(stripped) < 80:
            display = m.group(2).strip()
            cleaned = clean_tts_text(display)
            if cleaned: headings.append({"cleaned_text": cleaned, "display_text": display, "level": 3})
            continue
    return headings

def preprocess_text(text: str) -> str:
    cleaned_text = text.replace("\r\n", "\n")
    lines = cleaned_text.split('\n')
    for i in range(len(lines)):
        line = lines[i].strip()
        if re.match(r'^(#{1,6}|\*\*|__|\d+[\.\s]|[IVXLCDM]+\.\s|[A-Z]\.\s)', line) and not line.endswith('.'):
            lines[i] = line + "."
    cleaned_text = '\n'.join(lines)
    cleaned_text = cleaned_text.replace("\n\n", ".   ")
    cleaned_text = cleaned_text.replace("\n", " ")
    while "  " in cleaned_text: cleaned_text = cleaned_text.replace("  ", " ")
    return cleaned_text.strip()

raw_text = """# **셜록 홈즈의 모험 (The Adventures of Sherlock Holmes)**

## **1\. 보헤미아 왕국 스캔들 (A Scandal in Bohemia)**

셜록 홈즈는 언제나 여성의 지성과 냉철함을 높이 평가하지 않는 경향이 있었지만, 그가 유일하게 특별한 경외심과 존중을 담아 기억하는 여성이 있었습니다."""

headings = extract_markdown_headings(raw_text)

preprocessed = preprocess_text(raw_text)

# chunking
paragraphs = preprocessed.split(". ")
chunks = []
current_chunk = ""
for p in paragraphs:
    if not p.strip(): continue
    p = p + ". "
    if len(current_chunk) + len(p) < 800:
        current_chunk += p
    else:
        chunks.append(current_chunk)
        current_chunk = p
if current_chunk: chunks.append(current_chunk)

sentences = []
for chunk in chunks:
    tts_text = clean_tts_text(chunk)
    # Simulate edge-tts splitting on period
    for s in tts_text.split("."):
        if s.strip():
            sentences.append({"text": s.strip() + "."})

def annotate(sentences, headings):
    remaining = list(headings)
    for i, s in enumerate(sentences):
        s_text = s["text"].strip()
        matched = False
        for h in remaining[:3]:
            h_text = h["cleaned_text"].strip()
            
            s_super_clean = re.sub(r'[^\w가-힣]', '', s_text)
            h_super_clean = re.sub(r'[^\w가-힣]', '', h_text)
            
            is_match = False
            if s_super_clean == h_super_clean: is_match = True
            elif h_super_clean in s_super_clean: is_match = True
            elif s_super_clean in h_super_clean and len(s_super_clean) >= len(h_super_clean) * 0.5: is_match = True
            
            if is_match:
                s["type"] = "heading"
                remaining.remove(h)
                matched = True
                break
        if not matched: s["type"] = "text"
    return sentences

print("ANNOTATED SENTENCES:")
for s in annotate(sentences, headings):
    print(s)
