import re

s_text = "셜록 홈즈의 모험."
h_text = "셜록 홈즈의 모험"

s_super_clean = re.sub(r'[^\w가-힣]', '', s_text)
h_super_clean = re.sub(r'[^\w가-힣]', '', h_text)

print(f"s_text: '{s_text}' -> '{s_super_clean}'")
print(f"h_text: '{h_text}' -> '{h_super_clean}'")
print(f"Match: {s_super_clean == h_super_clean}")
