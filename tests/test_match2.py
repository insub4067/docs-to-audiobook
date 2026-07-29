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
    {"text": "1."},
    {"text": "보헤미아 왕국 스캔들."},
    {"text": "셜록 홈즈는 언제나 여성의 지성과..."}
]
headings = [{"cleaned_text": "1. 보헤미아 왕국 스캔들"}]

print("ANNOTATED SENTENCES:")
for s in annotate(sentences, headings):
    print(s)
