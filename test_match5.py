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

셜록 홈즈는 언제나 여성의 지성과 냉철함을 높이 평가하지 않는 경향이 있었지만, 그가 유일하게 특별한 경외심과 존중을 담아 기억하는 여성이 있었습니다. 그녀는 바로 오스트리아의 전 국왕이자 보헤미아의 세습 군주인 빌헬름 갓츠라이히 시기스문트 폰 오른슈타인 대공을 위기에 빠뜨렸던 전직 오페라 가수의 연인이자 모험가, 아이린 애들러(Irene Adler)입니다.

사건은 보헤미아의 국왕이 될 오른슈타인 대공이 정략결혼을 앞두고 과거에 아이린 애들러와 나누었던 친밀한 관계를 증명하는 한 장의 사진 때문에 홈즈를 찾아오면서 시작됩니다. 아이린 애들러는 대공이 결혼 소식을 알리자 복수심에 불타 그 사진을 대공의 약혼녀에게 보내 결혼을 파탄내겠다고 협박하고 있었습니다. 대공은 사채업자나 도둑을 고용해서라도 사진을 빼앗으려 했지만 실패했고, 결국 당대 최고의 탐정인 홈즈에게 의뢰를 맡기게 됩니다.

홈즈는 변장의 명수답게 노신부로 위장하여 아이린 애들러의 집에 잠입합니다. 그는 그녀의 약혼자 고트프레이 노튼(Godfrey Norton) 변호사가 급히 찾아와 교회에서 비밀리에 결혼식을 올리려 한다는 결정적인 정보를 입수합니다. 결혼식이 끝난 후 홈즈는 아이린 애들러가 사진을 숨겨둔 은닉처를 알아내기 위해 기발한 연극을 계획합니다.

그는 왓슨 박사에게 연막탄과 소란을 피우도록 지시한 뒤, 집 안으로 뛰어 들어가 "불이 났다\!"고 외칩니다. 평소 화재가 나면 가장 소중한 물건부터 챙기게 된다는 심리를 이용한 작전이었습니다. 사람들의 당황한 틈을 타 아이린 애들러는 자신이 사진을 숨겨둔 비밀 벽장으로 달려갔고, 홈즈는 그녀가 사진을 꺼내는 모습을 정확하게 포착해 냅니다."""

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

print("EXTRACTED HEADINGS:")
for h in headings: print(h)

print("\nANNOTATED SENTENCES:")
for s in annotate(sentences, headings):
    print(f"[{s.get('type')}] {s['text']}")
