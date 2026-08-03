"""provider_name("edge_tts" 또는 "google")으로 실제 어댑터를 고르는 팩토리.

어떤 provider_name을 쓸지는 호출부가 정한다 — 보통은
voice_catalog.provider_for_voice(voice_key)로 음성별 고정값을 구해서
넘긴다(voice_catalog.py의 설명 참고: 음성마다 합성 엔진이 고정되어
있고, 전역 스위치가 아니다).

의도적으로 인스턴스를 캐시하지 않는다 — 어댑터 생성 비용이 낮고(Google
쪽 클라이언트도 첫 synthesize 호출까지 지연 생성한다), 싱글턴으로
캐시하면 테스트에서 provider_name을 바꿔가며 검증하기 번거로워진다.
"""
from .base import TTSProvider


def get_tts_provider(provider_name: str) -> TTSProvider:
    if provider_name == "google":
        from .google_tts_adapter import GoogleTTSAdapter
        return GoogleTTSAdapter()
    from .edge_tts_adapter import EdgeTTSAdapter
    return EdgeTTSAdapter()
