import re

def clean_tts_text(text: str) -> str:
    t = re.sub(r'#+\s*', '', text)
    t = re.sub(r'[*_~`\\]', '', t)
    t = re.sub(r'>\s*', '', t)
    t = re.sub(r'([가-힣0-9])\s*\([A-Za-z0-9\s.,\-\'\"]+\)', r'\1', t)
    return t

lines = [
    "## 1. 보헤미아 왕국 스캔들",
    "1,보헤미아 왕국 스캔들 (A Scandal in Bohemia)",
    "ㄴ보헤미아 왕국 스캔들",
    "L보헤미아 왕국 스캔들",
    "1. 보헤미아 왕국 스캔들",
    "10. 귀족 신사 사건",
    "I. 보헤미아 왕국 스캔들",
    "L. 보헤미아 왕국 스캔들"
]

for stripped in lines:
    print(f"Text: {stripped}")
    
    # MD regex
    m2 = re.match(r'^(#{1,3})\s+(.+)$', stripped)
    if m2:
        print(f"  -> MD MATCHED!")
        continue
        
    # Old number regex (from yesterday)
    m_old = re.match(r'^(\*\*|__)?(\d+[\.\s]+.+?)\1?$', stripped)
    if m_old:
        print(f"  -> OLD MATCHED: {m_old.group(2)}")
        
    # Current regex
    m = re.match(r'^(\*\*|__)?((\d+[\.\s]+|[IVXLCDM]+\.\s+|[A-Z]\.\s+)(.+?))\1?$', stripped)
    if m:
        display = m.group(2).strip()
        cleaned = clean_tts_text(display)
        print(f"  -> NEW MATCHED! display: {display}, cleaned: {cleaned}")
    else:
        print("  -> NO MATCH")
