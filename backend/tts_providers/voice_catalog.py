"""공급자 중립 음성 키 <-> 공급자별 실제 음성 ID 매핑.

voice_key(예: "ko_male_warm")는 API 계약·프론트엔드·DB(background_synthesis_jobs.voice
컬럼)에 저장되는 값이고, 그대로 유지된다.

각 음성은 "provider" 필드로 실제 합성 엔진을 고정한다(음성별 고정 —
전역 스위치가 아니다). 원래 있던 두 음성(현수/선희)은 edge-tts 태생이라
그대로 edge_tts에 고정하고, 나중에 추가한 두 음성(카론/코어)은 Google
Chirp3-HD 전용이라 google에 고정한다 — edge-tts에는 대응하는 음성이
아예 없어서(카론/코어는 edge-tts 정체성이 없는, 새로 만든 음성) 굳이
대체 음성을 끼워 맞추지 않는다. 이전에는 TTS_PROVIDER 환경변수 하나로
모든 음성을 한꺼번에 전환했는데, 그러면 카론/코어에 억지로 끼워 맞춘
edge-tts 대체 음성(InJoon/SunHi)이 튀어나오는 문제가 있었다.

Google 쪽 음성 ID는 실제 서비스 계정으로 라이브 합성까지 확인했다
(Neural2-A/C, Chirp3-HD-Charon/Kore).
"""

VOICE_CATALOG = {
    "ko_male_warm": {
        "friendly_name": "현수 (자연스러운 낭독 - 남성)",
        "description": "억양이 자연스럽고, 한글과 영어가 섞인 문장도 매끄럽게 읽습니다.",
        "gender": "Male",
        "locale": "ko-KR",
        "tone": "natural",
        "use_case": ["novel", "audiobook", "documentation", "long_text"],
        "provider": "edge_tts",
        "provider_ids": {
            "edge_tts": "ko-KR-HyunsuMultilingualNeural",
            "google": "ko-KR-Neural2-C",
        },
    },
    "ko_female_calm": {
        "friendly_name": "선희 (차분한 낭독 - 여성)",
        "description": "단정하고 차분한 여성 음성으로, 정보 전달이나 긴 호흡의 낭독에 적합합니다.",
        "gender": "Female",
        "locale": "ko-KR",
        "tone": "formal",
        "use_case": ["news", "education", "audiobook", "long_text"],
        "provider": "edge_tts",
        "provider_ids": {
            "edge_tts": "ko-KR-SunHiNeural",
            "google": "ko-KR-Neural2-A",
        },
    },
    "ko_male_charon": {
        "friendly_name": "카론 (Google 프리미엄 낭독 - 남성)",
        "description": "Google Cloud의 최신 Chirp3 HD 모델 음성입니다.",
        "gender": "Male",
        "locale": "ko-KR",
        "tone": "natural",
        "use_case": ["novel", "audiobook", "documentation", "long_text"],
        "provider": "google",
        "provider_ids": {
            "google": "ko-KR-Chirp3-HD-Charon",
        },
    },
    "ko_female_kore": {
        "friendly_name": "코어 (Google 프리미엄 낭독 - 여성)",
        "description": "Google Cloud의 최신 Chirp3 HD 모델 음성입니다.",
        "gender": "Female",
        "locale": "ko-KR",
        "tone": "natural",
        "use_case": ["novel", "audiobook", "documentation", "long_text"],
        "provider": "google",
        "provider_ids": {
            "google": "ko-KR-Chirp3-HD-Kore",
        },
    },
}

# VOICE_CATALOG에 적은 순서가 곧 노출 순서 — 첫 번째가 기본값이다.
VOICE_KEYS = list(VOICE_CATALOG.keys())
DEFAULT_VOICE_KEY = VOICE_KEYS[0]

# 이 마이그레이션 이전에 저장된 값(background_synthesis_jobs.voice 컬럼의
# 기존 행, 캐시된 구버전 프론트가 보내는 요청)은 edge-tts 원본 short_name
# ("ko-KR-HyunsuMultilingualNeural") 그대로다. 역방향 조회로 두 포맷을
# 모두 받아들인다. edge_tts 매핑이 없는 음성(카론/코어)은 건너뛴다.
_LEGACY_SHORT_NAME_TO_KEY: dict[str, str] = {}
for _key, _meta in VOICE_CATALOG.items():
    _edge_id = _meta["provider_ids"].get("edge_tts")
    if _edge_id:
        _LEGACY_SHORT_NAME_TO_KEY.setdefault(_edge_id, _key)


def find_voice_key(value: str) -> str | None:
    """voice_key 또는 예전 edge-tts short_name을 받아 정규화된 voice_key로
    바꾼다. 둘 다 아니면 None."""
    if value in VOICE_CATALOG:
        return value
    return _LEGACY_SHORT_NAME_TO_KEY.get(value)


def resolve_voice_key(value: str) -> str:
    """find_voice_key와 같지만, 모르는 값이면 기본 음성으로 대체한다.
    합성 요청이나 재개된 백그라운드 작업이 알 수 없는 voice 값 때문에
    통째로 실패하는 것보다 기본 음성으로라도 진행하는 편이 낫다."""
    return find_voice_key(value) or DEFAULT_VOICE_KEY


def provider_for_voice(voice_key: str) -> str:
    """voice_key에 고정된 합성 엔진 이름("edge_tts" 또는 "google")을 반환한다."""
    meta = VOICE_CATALOG.get(voice_key) or VOICE_CATALOG[DEFAULT_VOICE_KEY]
    return meta["provider"]


def provider_voice_id(voice_key: str, provider_name: str) -> str:
    """voice_key를 공급자(provider_name)의 실제 음성 ID로 변환한다."""
    meta = VOICE_CATALOG.get(voice_key) or VOICE_CATALOG[DEFAULT_VOICE_KEY]
    return meta["provider_ids"][provider_name]
