"""upload_audiobook_objects — 오디오와 문장 JSON은 항상 함께 존재해야 한다.

이 불변식은 news.py·library.py·tts.py 세 곳에 같은 코드로 복사돼 있었고,
보상 삭제를 검증하는 테스트는 tts.py 경로에만 있었다(test_background_jobs).
하나로 합치면서 불변식 자체를 여기서 검증한다 — 세 호출부가 모두 이 함수에
기대므로, 여기가 깨지면 세 기능이 함께 깨진다.
"""
from unittest.mock import MagicMock

import pytest

from state import object_paths, upload_audiobook_objects


def _supabase_with_storage(storage):
    supabase = MagicMock()
    supabase.storage.from_.return_value = storage
    return supabase


def test_uploads_audio_and_sentences_side_by_side():
    storage = MagicMock()

    audio_path = upload_audiobook_objects(
        _supabase_with_storage(storage), "user-1", "book-1", b"mp3", [{"text": "가"}]
    )

    expected_audio, expected_sentences = object_paths("user-1", "book-1")
    assert audio_path == expected_audio
    uploaded = [call.args[0] for call in storage.upload.call_args_list]
    assert uploaded == [expected_audio, expected_sentences]


def test_sentences_are_stored_as_utf8_json_without_escapes():
    """한글이 \\uXXXX로 escape되면 파일이 몇 배로 커진다."""
    storage = MagicMock()

    upload_audiobook_objects(
        _supabase_with_storage(storage), "user-1", "book-1", b"mp3", [{"text": "안녕"}]
    )

    sentences_body = storage.upload.call_args_list[1].args[1]
    assert "안녕".encode("utf-8") in sentences_body


def test_audio_is_removed_when_sentences_upload_fails():
    """문장 업로드가 실패했는데 mp3만 남으면 하이라이트 없는 반쪽짜리
    오디오북이 버킷에 영구히 남는다."""
    storage = MagicMock()
    storage.upload.side_effect = [None, RuntimeError("sentences failed")]

    with pytest.raises(RuntimeError, match="sentences failed"):
        upload_audiobook_objects(
            _supabase_with_storage(storage), "user-1", "book-1", b"mp3", [{"text": "가"}]
        )

    expected_audio, _ = object_paths("user-1", "book-1")
    storage.remove.assert_called_once_with([expected_audio])


def test_audio_upload_failure_does_not_try_to_remove():
    """오디오 자체가 안 올라갔으면 지울 것도 없다 — 여기서 remove를 부르면
    존재하지 않는 객체 삭제로 원래 오류가 가려진다."""
    storage = MagicMock()
    storage.upload.side_effect = RuntimeError("audio failed")

    with pytest.raises(RuntimeError, match="audio failed"):
        upload_audiobook_objects(
            _supabase_with_storage(storage), "user-1", "book-1", b"mp3", [{"text": "가"}]
        )

    storage.remove.assert_not_called()


def test_orphan_pair_is_removed_when_the_db_row_fails():
    """파일을 올린 뒤 audiobooks insert가 실패하면, 그 파일들을 가리키는
    것이 아무것도 없어 버킷에만 영영 남는다."""
    from state import remove_audiobook_objects

    storage = MagicMock()
    supabase = _supabase_with_storage(storage)

    remove_audiobook_objects(supabase, "user-1", "book-1")

    storage.remove.assert_called_once_with(list(object_paths("user-1", "book-1")))


def test_cleanup_failure_does_not_mask_the_original_error():
    """호출부는 이미 다른 실패를 처리하는 중이다. 정리에 또 실패했다고
    예외를 올리면 무엇이 근본 원인인지 알 수 없게 된다."""
    from state import remove_audiobook_objects

    storage = MagicMock()
    storage.remove.side_effect = RuntimeError("storage down")

    remove_audiobook_objects(_supabase_with_storage(storage), "user-1", "book-1")
