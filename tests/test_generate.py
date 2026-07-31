import pytest
import asyncio
from unittest.mock import patch, MagicMock
from main import synthesize_document, synthesize_chunk

@pytest.mark.asyncio
async def test_synthesize_chunk_success():
    # We want to mock edge_tts.Communicate so it doesn't actually synthesize anything
    with patch('main.edge_tts.Communicate') as MockCommunicate:
        mock_instance = MagicMock()
        
        async def mock_stream():
            yield {"type": "audio", "data": b"fake_audio_data"}
            yield {"type": "SentenceBoundary"}
            
        mock_instance.stream.return_value = mock_stream()
        MockCommunicate.return_value = mock_instance
        
        idx, audio, _ = await synthesize_chunk(0, "Test chunk", "ko-KR-SunHiNeural", "1.0", "0.0", max_attempts=1)
        
        assert idx == 0
        assert audio == b"fake_audio_data"

@pytest.mark.asyncio
async def test_synthesize_chunk_failure():
    # If the TTS engine raises an exception, we want to see if it retries and fails
    with patch('main.edge_tts.Communicate') as MockCommunicate:
        mock_instance = MagicMock()
        mock_instance.stream.side_effect = Exception("TTS failed")
        MockCommunicate.return_value = mock_instance
        
        with pytest.raises(Exception) as exc_info:
            await synthesize_chunk(0, "Test chunk", "ko-KR-SunHiNeural", "1.0", "0.0", max_attempts=1)
            
        assert "TTS failed" in str(exc_info.value)
