import asyncio
import edge_tts

async def run_test(text, label):
    print(f"Testing monkeypatched: {label}...")
    try:
        communicate = edge_tts.Communicate("dummy", voice="ko-KR-SunHiNeural")
        communicate.texts = [text.encode("utf-8")]
        
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio":
                audio_data += chunk.get("data")
        print(f"✅ Success! Size: {len(audio_data)} bytes")
    except Exception as e:
        print(f"❌ Failed: {e}")

async def main():
    # Test A: Plain text with monkeypatch
    await run_test("안녕하세요. 반갑습니다.", "Plain Text (No break tag)")
    
    # Test B: Text with break tag
    await run_test("안녕하세요. <break time=\"500ms\"/> 반갑습니다.", "With Break Tag")

if __name__ == "__main__":
    asyncio.run(main())
