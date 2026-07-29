import re

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

sentences = [
    {"text": "셜록 홈즈의 모험.. 1. 보헤미아 왕국 스캔들.. 셜록 홈즈는 언제나 여성의 지성과 냉철함을 높이 평가하지 않는 경향이 있었지만, 그가 유일하게 특별한 경외심과 존중을 담아 기억하는 여성이 있었습니다."}
]
headings = [
    {"cleaned_text": "셜록 홈즈의 모험", "display_text": "셜록 홈즈의 모험 (The Adventures of Sherlock Holmes)", "level": 1},
    {"cleaned_text": "1. 보헤미아 왕국 스캔들", "display_text": "1. 보헤미아 왕국 스캔들 (A Scandal in Bohemia)", "level": 2}
]

print("ANNOTATED SENTENCES:")
for s in annotate(sentences, headings):
    print(s)
