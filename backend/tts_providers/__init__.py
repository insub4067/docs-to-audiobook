"""TTS_PROVIDER 환경변수(기본값 edge_tts)로 실제 공급자를 고르는 팩토리.

의도적으로 인스턴스를 캐시하지 않는다 — 어댑터 생성 비용이 낮고(Google
쪽 클라이언트도 첫 synthesize 호출까지 지연 생성한다), 싱글턴으로
캐시하면 테스트에서 TTS_PROVIDER를 바꿔가며 검증하기 번거로워진다.
"""
import os

from .base import TTSProvider


def get_tts_provider() -> TTSProvider:
    provider_name = os.environ.get("TTS_PROVIDER", "edge_tts").strip().lower()
    if provider_name == "google":
        from .google_tts_adapter import GoogleTTSAdapter
        return GoogleTTSAdapter()
    from .edge_tts_adapter import EdgeTTSAdapter
    return EdgeTTSAdapter()
