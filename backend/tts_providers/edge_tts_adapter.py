"""edge-tts(MS Edge 낭독 엔진, 비공식 API) 어댑터. 기존 routes/tts.py에
직접 박혀 있던 edge_tts 호출부를 그대로 옮긴 것 — 동작은 바뀌지 않는다."""
import asyncio

import edge_tts

from .base import SentenceBoundary, TTSProvider, VoiceOption
from .voice_catalog import VOICE_CATALOG, VOICE_KEYS, provider_voice_id

# 이전에는 문서의 모든 청크를 상한 없이 asyncio.gather로 한꺼번에 띄웠고
# (2만 자 = 25개 동시), 여러 작업이 겹치면 수백 개까지 늘어나 간헐적 연결
# 끊김이 났다. 작업 수와 무관하게 전역으로 묶는다.
_CONCURRENCY = asyncio.Semaphore(8)


class EdgeTTSAdapter(TTSProvider):
    name = "edge_tts"

    async def list_voices(self) -> list[VoiceOption]:
        try:
            all_voices = await edge_tts.VoicesManager.create()
            by_short_name = {v.get("ShortName"): v for v in all_voices.voices}
        except Exception:
            by_short_name = {}

        result: list[VoiceOption] = []
        for key in VOICE_KEYS:
            meta = VOICE_CATALOG[key]
            short_name = meta["provider_ids"]["edge_tts"]
            live = by_short_name.get(short_name, {})
            result.append({
                "key": key,
                "name": live.get("Name", short_name),
                "gender": live.get("Gender", meta["gender"]),
                "locale": live.get("Locale", meta["locale"]),
                "friendly_name": meta["friendly_name"],
                "description": meta["description"],
                "tone": meta["tone"],
                "use_case": meta["use_case"],
            })
        return result

    async def synthesize(self, text: str, voice_key: str, rate: str, pitch: str) -> tuple[bytes, list[SentenceBoundary]]:
        voice_id = provider_voice_id(voice_key, self.name)
        async with _CONCURRENCY:
            communicate = edge_tts.Communicate(text, voice=voice_id, rate=rate, pitch=pitch)
            # bytes는 불변이라 += 누적은 조각마다 전체 복사본을 새로 만든다.
            # 조각을 모아 마지막에 한 번만 합친다.
            audio_parts = []
            sentences: list[SentenceBoundary] = []
            async for msg in communicate.stream():
                if msg.get("type") == "audio":
                    audio_parts.append(msg.get("data"))
                elif msg.get("type") == "SentenceBoundary":
                    offset_ms = msg.get("offset", 0) // 10000
                    duration_ms = msg.get("duration", 0) // 10000
                    sentences.append({
                        "text": msg.get("text", ""),
                        "start": offset_ms,
                        "end": offset_ms + duration_ms,
                    })
            audio_data = b"".join(audio_parts)
            audio_parts.clear()
        return audio_data, sentences
