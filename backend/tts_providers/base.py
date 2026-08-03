"""공급자별 TTS 구현이 지켜야 할 추상 인터페이스.

특정 공급자(edge-tts, Google Cloud TTS 등)에 의존하는 코드는 이 파일
바깥(각 어댑터 모듈)에만 있어야 한다 — routes/tts.py는 이 인터페이스만
보고 어떤 공급자가 실제로 붙어있는지 몰라야 한다.
"""
from abc import ABC, abstractmethod
from typing import TypedDict


class VoiceOption(TypedDict):
    key: str
    name: str
    gender: str
    locale: str
    friendly_name: str
    description: str
    tone: str
    use_case: list[str]


class SentenceBoundary(TypedDict):
    text: str
    start: int
    end: int


class TTSProvider(ABC):
    """모든 TTS 공급자 어댑터가 구현해야 하는 인터페이스."""

    name: str

    @abstractmethod
    async def list_voices(self) -> list[VoiceOption]:
        """공급자 중립 음성 키(voice_catalog.VOICE_CATALOG)를 기준으로
        노출 가능한 음성 목록을 반환한다."""
        raise NotImplementedError

    @abstractmethod
    async def synthesize(self, text: str, voice_key: str, rate: str, pitch: str) -> tuple[bytes, list[SentenceBoundary]]:
        """text(순수 낭독 텍스트, 청크 단위)를 오디오로 합성한다.

        voice_key: 공급자 중립 내부 음성 키(예: "ko_male_warm") — 실제
            공급자별 음성 ID로의 변환은 어댑터 내부에서 한다.
        rate/pitch: edge-tts 표기 그대로("+10%", "+0Hz") 받는다. 이 값이
            API 계약·프론트엔드까지 그대로 노출돼 있어 바꾸지 않았다 —
            edge-tts가 아닌 어댑터는 내부에서 자기 SDK 포맷으로 변환한다.
        반환: (mp3 오디오 바이트, 문장 경계 리스트[ms 단위 start/end])
        """
        raise NotImplementedError
