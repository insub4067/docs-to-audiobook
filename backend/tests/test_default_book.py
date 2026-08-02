"""기본 제공 오디오북의 캐시 키/복원 로직 테스트.

이전에 축약본(3챕터)으로 만든 오디오가 전문(12챕터)으로 바꾼 뒤에도
계속 재사용되는 회귀가 있었다. 원인은 캐시 키가 음성만 반영하고 원문
내용을 반영하지 않았던 것이라, 그 수정(_default_book_fingerprint)이
실제로 동작하는지가 이 파일의 핵심이다.
"""
import pytest
from routes import default_book


def test_default_book_uses_demian_source():
    assert default_book.DEFAULT_BOOK_SOURCE.endswith("samples/demian.txt")
    assert default_book.DEFAULT_BOOK_TITLE == "데미안"
    with open(default_book.DEFAULT_BOOK_SOURCE, encoding="utf-8") as source:
        assert source.readline().strip() == "제1장 두 세계"


@pytest.fixture
def reset_default_book_state():
    """default_book_state는 모듈 전역 dict라 테스트 간에 새어나간다."""
    original = dict(default_book.default_book_state)
    yield
    default_book.default_book_state.clear()
    default_book.default_book_state.update(original)


def test_fingerprint_changes_with_content_and_voice(tmp_path, monkeypatch):
    source = tmp_path / "book.md"
    source.write_text("원본 내용")
    monkeypatch.setattr(default_book, "DEFAULT_BOOK_SOURCE", str(source))
    monkeypatch.setattr(default_book, "DEFAULT_BOOK_VOICE", "voiceA")

    fp_original = default_book._default_book_fingerprint()
    assert fp_original.startswith("voiceA.")

    # 같은 입력이면 항상 같은 지문이어야 한다(캐시 키로 쓰이므로 결정적이어야 함)
    assert default_book._default_book_fingerprint() == fp_original

    # 원문 내용이 바뀌면 지문도 바뀌어야 한다 — 이게 실제로 고친 버그다.
    source.write_text("완전히 다른 내용으로 교체됨")
    fp_after_content_change = default_book._default_book_fingerprint()
    assert fp_after_content_change != fp_original

    # 음성이 바뀌어도 지문이 바뀌어야 한다.
    monkeypatch.setattr(default_book, "DEFAULT_BOOK_VOICE", "voiceB")
    fp_after_voice_change = default_book._default_book_fingerprint()
    assert fp_after_voice_change != fp_after_content_change
    assert fp_after_voice_change.startswith("voiceB.")


def test_paths_and_remote_keys_share_the_same_fingerprint(tmp_path, monkeypatch):
    source = tmp_path / "book.md"
    source.write_text("내용")
    monkeypatch.setattr(default_book, "DEFAULT_BOOK_SOURCE", str(source))
    monkeypatch.setattr(default_book, "DEFAULT_BOOK_VOICE", "voiceA")
    monkeypatch.setattr(default_book, "DEFAULT_BOOK_DIR", str(tmp_path / "default_book"))

    fp = default_book._default_book_fingerprint()
    audio_path, meta_path = default_book.default_book_paths()
    remote_audio, remote_meta = default_book.default_book_remote_keys()

    assert fp in audio_path
    assert fp in meta_path
    assert fp in remote_audio
    assert fp in remote_meta


@pytest.mark.asyncio
async def test_prepare_default_book_from_cache_disk_hit(tmp_path, monkeypatch, reset_default_book_state):
    source = tmp_path / "book.md"
    source.write_text("내용")
    monkeypatch.setattr(default_book, "DEFAULT_BOOK_SOURCE", str(source))
    monkeypatch.setattr(default_book, "DEFAULT_BOOK_VOICE", "voiceA")
    monkeypatch.setattr(default_book, "DEFAULT_BOOK_DIR", str(tmp_path / "default_book"))

    audio_path, meta_path = default_book.default_book_paths()
    import os
    os.makedirs(os.path.dirname(audio_path), exist_ok=True)
    open(audio_path, "wb").write(b"audio")
    open(meta_path, "w").write("{}")

    result = await default_book.prepare_default_book_from_cache()

    assert result is True
    assert default_book.default_book_state["status"] == "ready"


@pytest.mark.asyncio
async def test_prepare_default_book_from_cache_cloud_hit(tmp_path, monkeypatch, reset_default_book_state):
    source = tmp_path / "book.md"
    source.write_text("내용")
    monkeypatch.setattr(default_book, "DEFAULT_BOOK_SOURCE", str(source))
    monkeypatch.setattr(default_book, "DEFAULT_BOOK_VOICE", "voiceA")
    # 디스크에는 없다 — 클라우드에서 복구되는 경로를 검증한다
    monkeypatch.setattr(default_book, "DEFAULT_BOOK_DIR", str(tmp_path / "empty_default_book"))
    monkeypatch.setattr(default_book, "_restore_default_book_from_cloud", lambda a, m: True)

    result = await default_book.prepare_default_book_from_cache()

    assert result is True
    assert default_book.default_book_state["status"] == "ready"


@pytest.mark.asyncio
async def test_prepare_default_book_from_cache_miss(tmp_path, monkeypatch, reset_default_book_state):
    source = tmp_path / "book.md"
    source.write_text("내용")
    monkeypatch.setattr(default_book, "DEFAULT_BOOK_SOURCE", str(source))
    monkeypatch.setattr(default_book, "DEFAULT_BOOK_VOICE", "voiceA")
    monkeypatch.setattr(default_book, "DEFAULT_BOOK_DIR", str(tmp_path / "empty_default_book"))
    monkeypatch.setattr(default_book, "_restore_default_book_from_cloud", lambda a, m: False)

    result = await default_book.prepare_default_book_from_cache()

    # 디스크에도 클라우드에도 없으면 합성하지 않고 pending으로 둔다.
    # (합성은 실제 요청이 올 때 generate_default_book이 한다.)
    assert result is False
    assert default_book.default_book_state["status"] == "pending"
