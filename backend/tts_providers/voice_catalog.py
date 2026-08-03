"""공급자 중립 음성 키 <-> 공급자별 실제 음성 ID 매핑.

voice_key(예: "ko_male_warm")는 API 계약·프론트엔드·DB(background_synthesis_jobs.voice
컬럼)에 저장되는 값이고, TTS_PROVIDER 환경변수를 바꿔도 그대로 유지된다.
실제 공급자별 음성 ID는 각 어댑터가 provider_voice_id()로 이 표에서 찾아 쓴다.

Google 쪽 음성 ID는 실제 서비스 계정으로 라이브 합성까지 확인했다
(Neural2-A/C, Chirp3-HD-Charon/Kore). edge-tts는 ko-KR 음성이 3개뿐이라
(Hyunsu/InJoon 남성, SunHi 여성) ko_female_calm과 ko_female_kore는
edge-tts로 전환 시 둘 다 SunHi로 겹친다 — 대응하는 두 번째 여성 음성이
없어서 어쩔 수 없다.
"""

VOICE_CATALOG = {
    "ko_male_warm": {
        "friendly_name": "현수 (자연스러운 낭독 - 남성)",
        "description": "억양이 자연스럽고, 한글과 영어가 섞인 문장도 매끄럽게 읽습니다.",
        "gender": "Male",
        "locale": "ko-KR",
        "tone": "natural",
        "use_case": ["novel", "audiobook", "documentation", "long_text"],
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
        "provider_ids": {
            "edge_tts": "ko-KR-InJoonNeural",
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
        "provider_ids": {
            "edge_tts": "ko-KR-SunHiNeural",
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
# 모두 받아들인다. 여러 voice_key가 같은 edge_tts id를 공유할 수 있어서
# (예: ko_female_calm과 ko_female_kore가 둘 다 SunHi) 먼저 등장한 항목이
# 이기게 한다 — 나중 항목이 덮어쓰면 예전에 저장된 값이 전혀 다른(방금
# 새로 추가된) 음성으로 조용히 바뀌어버린다.
_LEGACY_SHORT_NAME_TO_KEY: dict[str, str] = {}
for _key, _meta in VOICE_CATALOG.items():
    _LEGACY_SHORT_NAME_TO_KEY.setdefault(_meta["provider_ids"]["edge_tts"], _key)


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


def provider_voice_id(voice_key: str, provider_name: str) -> str:
    """voice_key를 공급자(provider_name)의 실제 음성 ID로 변환한다."""
    meta = VOICE_CATALOG.get(voice_key) or VOICE_CATALOG[DEFAULT_VOICE_KEY]
    return meta["provider_ids"][provider_name]
