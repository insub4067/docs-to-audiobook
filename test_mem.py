import time
import os
import psutil

process = psutil.Process(os.getpid())
print(f"Memory before import: {process.memory_info().rss / 1024 / 1024:.2f} MB")

try:
    from supertonic import TTS
    print(f"Memory after import: {process.memory_info().rss / 1024 / 1024:.2f} MB")
    
    tts = TTS(auto_download=True)
    print(f"Memory after TTS init: {process.memory_info().rss / 1024 / 1024:.2f} MB")
    
    style = tts.get_voice_style(voice_name="M1")
    wav, dur = tts.synthesize("테스트 문장입니다.", voice_style=style, lang="ko")
    print(f"Memory after synthesize: {process.memory_info().rss / 1024 / 1024:.2f} MB")
except ImportError:
    print("Supertonic is not installed.")
