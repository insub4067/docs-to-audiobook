"""Google Cloud Text-to-Speech 어댑터.

문장 경계(타이밍) 확보 방식: edge-tts는 스트리밍 중 SentenceBoundary
이벤트를 그대로 준다. Google Cloud TTS는 그런 이벤트가 없는 대신 SSML
<mark> 태그 + enable_time_pointing=[SSML_MARK]로 각 마크가 오디오의 몇
초 지점에 나오는지 돌려준다(v1beta1 API 전용 기능) — 문장마다 앞에
마크를 심어 그 시각을 문장 시작 시각으로 쓴다. 텍스트 맨 끝에도 마크를
하나 더 심어(내용 없는 마크) 마지막 문장의 끝 시각까지 실측한다.

주의(실사용 중 발견): Chirp3-HD 계열 음성은 SSML mark 타임포인팅을
아예 지원하지 않는다 — 요청은 성공하고 오디오도 정상 나오지만
response.timepoints가 빈 채로 온다(Neural2/WaveNet/Standard는 정상
동작 확인함). 이 경우 문장별 시작/끝을 전혀 알 수 없어 처음엔 앞
문장들의 글자당 평균 속도로 추정했는데, routes/tts.py가 청크 끝 시각을
다음 청크의 시작 오프셋으로 그대로 이어붙이는 구조라 문서가 길어질수록
오차가 누적돼 읽기모드 하이라이트가 점점 어긋났다. mark가 비어 있으면
mutagen으로 오디오 전체 길이를 실측해(청크 경계는 정확해짐) 문장
내부 경계만 글자 수 비율로 나누는 방식으로 대체한다.

rate/pitch 변환도 근사치다: edge-tts의 "+N%"는 Google의 speaking_rate
배수로 비교적 자연스럽게 옮겨지지만("+10%" -> 1.10), "+NHz" 형태의 pitch는
사람마다 다른 기준 주파수를 알아야 정확히 semitone으로 옮길 수 있어
10Hz ≈ 1반음이라는 거친 근사만 적용했다. 실사용 시 청감으로 재조정 필요.
"""
import json
import os
import re
from xml.sax.saxutils import escape

from .base import SentenceBoundary, TTSProvider, VoiceOption
from .voice_catalog import VOICE_CATALOG, VOICE_KEYS, provider_voice_id

# Google Cloud TTS 동시 요청 상한. 공식 API라 정식 쿼터가 있지만(기본
# 분당 1000요청 안팎), 문서 하나가 수십 개 청크로 쪼개져 gather로
# 한꺼번에 몰리는 걸 막기 위해 기본값을 넉넉히 둔다. 실제 쿼터에 맞춰
# 환경변수로 조정 가능.
_CONCURRENCY_LIMIT = int(os.environ.get("GOOGLE_TTS_CONCURRENCY", "16"))

_PERCENT_RE = re.compile(r"([+-]?\d+(?:\.\d+)?)\s*%")
_HZ_RE = re.compile(r"([+-]?\d+(?:\.\d+)?)\s*Hz", re.IGNORECASE)


def _parse_rate_to_speaking_rate(rate: str) -> float:
    """edge-tts 표기("+10%")를 Google의 speaking_rate 배수(1.0=보통)로 변환한다."""
    match = _PERCENT_RE.search(rate or "")
    percent = float(match.group(1)) if match else 0.0
    return max(0.25, min(4.0, 1 + percent / 100))


def _parse_pitch_to_semitones(pitch: str) -> float:
    """edge-tts 표기("+0Hz")를 Google의 semitone 단위 pitch로 근사 변환한다."""
    match = _HZ_RE.search(pitch or "")
    hz = float(match.group(1)) if match else 0.0
    return max(-20.0, min(20.0, hz / 10))


def _split_sentences(text: str) -> list[str]:
    """routes/tts.py의 split_tts_chunks와 동일하게 ". " 기준으로 나눈다 —
    문장 경계 판정 방식을 앱 전체에서 일관되게 유지하기 위함."""
    parts = [p.strip() for p in text.split(". ") if p.strip()]
    return parts or [text]


def _proportional_sentence_boundaries(sentences_text: list[str], audio_data: bytes) -> list[SentenceBoundary]:
    """SSML mark 타임포인팅을 지원하지 않는 음성(Chirp3-HD 등)을 위한
    대체 방식. 오디오 전체 길이는 mutagen으로 정확히 실측하므로 청크
    경계(다음 청크 오프셋)는 정확하다 — 문장 내부 경계만 글자 수 비율로
    나눠 근사한다."""
    from io import BytesIO
    from mutagen.mp3 import MP3

    total_ms = MP3(fileobj=BytesIO(audio_data)).info.length * 1000
    total_chars = sum(len(s) for s in sentences_text) or 1

    sentences: list[SentenceBoundary] = []
    offset = 0.0
    for sentence_text in sentences_text:
        duration = total_ms * (len(sentence_text) / total_chars)
        end = offset + duration
        sentences.append({"text": sentence_text, "start": int(offset), "end": int(end)})
        offset = end
    return sentences


class GoogleTTSAdapter(TTSProvider):
    name = "google"

    def __init__(self) -> None:
        self._client = None
        self._semaphore = None

    def _get_semaphore(self):
        import asyncio
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(_CONCURRENCY_LIMIT)
        return self._semaphore

    def _get_client(self):
        if self._client is None:
            from google.cloud import texttospeech_v1beta1 as texttospeech

            creds_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
            if creds_json:
                # Fly.io/Render처럼 파일 마운트 없이 대시보드 환경변수로만
                # 자격증명을 넣을 수 있는 배포 환경을 고려한 경로.
                from google.oauth2 import service_account

                info = json.loads(creds_json)
                credentials = service_account.Credentials.from_service_account_info(info)
                self._client = texttospeech.TextToSpeechAsyncClient(credentials=credentials)
            else:
                # GOOGLE_APPLICATION_CREDENTIALS(파일 경로) 등 표준 ADC
                # 방식이면 인증정보를 넘기지 않아도 라이브러리가 알아서 찾는다.
                self._client = texttospeech.TextToSpeechAsyncClient()
        return self._client

    async def list_voices(self) -> list[VoiceOption]:
        # edge-tts처럼 공급자에게 매번 실제 존재 여부를 조회하지 않고
        # 카탈로그를 그대로 신뢰한다 — Google 음성 목록은 edge-tts만큼
        # 자주 바뀌지 않고, 잘못된 음성 ID는 합성 시점에 바로 에러로 드러난다.
        return [
            {
                "key": key,
                "name": VOICE_CATALOG[key]["friendly_name"],
                "gender": VOICE_CATALOG[key]["gender"],
                "locale": VOICE_CATALOG[key]["locale"],
                "friendly_name": VOICE_CATALOG[key]["friendly_name"],
                "description": VOICE_CATALOG[key]["description"],
                "tone": VOICE_CATALOG[key]["tone"],
                "use_case": VOICE_CATALOG[key]["use_case"],
            }
            for key in VOICE_KEYS
        ]

    async def synthesize(self, text: str, voice_key: str, rate: str, pitch: str) -> tuple[bytes, list[SentenceBoundary]]:
        from google.cloud import texttospeech_v1beta1 as texttospeech

        voice_id = provider_voice_id(voice_key, self.name)
        meta = VOICE_CATALOG.get(voice_key) or VOICE_CATALOG[VOICE_KEYS[0]]
        sentences_text = _split_sentences(text)

        ssml_parts = ["<speak>"]
        for i, sentence in enumerate(sentences_text):
            ssml_parts.append(f'<mark name="s{i}"/>{escape(sentence)}. ')
        # 마지막 문장의 정확한 끝 시각을 실측하기 위한 마크 — 뒤에 텍스트가
        # 없어도 그 시점의 오디오 위치를 timepoints에 넣어준다.
        ssml_parts.append('<mark name="end"/>')
        ssml_parts.append("</speak>")
        ssml = "".join(ssml_parts)

        request = texttospeech.SynthesizeSpeechRequest(
            input=texttospeech.SynthesisInput(ssml=ssml),
            voice=texttospeech.VoiceSelectionParams(language_code=meta["locale"], name=voice_id),
            audio_config=texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                speaking_rate=_parse_rate_to_speaking_rate(rate),
                pitch=_parse_pitch_to_semitones(pitch),
            ),
            enable_time_pointing=[texttospeech.SynthesizeSpeechRequest.TimepointType.SSML_MARK],
        )

        async with self._get_semaphore():
            client = self._get_client()
            response = await client.synthesize_speech(request=request)

        audio_data = response.audio_content
        # marks_ms[i]는 문장 i의 시작, marks_ms[-1]은 트레일링 "end" 마크라
        # 정상 지원 음성이면 항상 len(sentences_text) + 1개가 온다. Chirp3-HD
        # 처럼 아예 지원하지 않는 음성은 timepoints가 빈 채로 온다 —
        # 그런 경우엔 실측한 오디오 길이 기반 근사로 대체한다.
        marks_ms = [tp.time_seconds * 1000 for tp in response.timepoints]

        if len(marks_ms) >= len(sentences_text) + 1:
            sentences: list[SentenceBoundary] = [
                {"text": sentence_text, "start": int(marks_ms[i]), "end": int(marks_ms[i + 1])}
                for i, sentence_text in enumerate(sentences_text)
            ]
        else:
            sentences = _proportional_sentence_boundaries(sentences_text, audio_data)

        return audio_data, sentences
