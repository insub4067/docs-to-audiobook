import asyncio
import edge_tts

async def main():
    text = "안녕하세요. 반가워요! 오늘은 날씨가 참 좋네요."
    voice = "ko-KR-SunHiNeural"
    communicate = edge_tts.Communicate(text, voice=voice)
    
    async for msg in communicate.stream():
        m_type = msg.get("type")
        if m_type != "audio":
            print(f"Message: {msg}")

if __name__ == "__main__":
    asyncio.run(main())
