import pytest
from state import read_upload_limited, save_upload_limited, enforce_rate_limit
from fastapi import HTTPException
import os

@pytest.mark.asyncio
async def test_upload_limits():
    
    class MockUploadFile:
        def __init__(self, chunks):
            self.chunks = chunks
        async def read(self, size=-1):
            return self.chunks.pop(0) if self.chunks else b""

    # Test read_upload_limited
    content = await read_upload_limited(MockUploadFile([b"12345"]), 10)
    assert content == b"12345"
    
    # Test exceeding limit
    with pytest.raises(HTTPException) as exc_info:
        await read_upload_limited(MockUploadFile([b"123456789012"]), 10)
    assert exc_info.value.status_code == 413

@pytest.mark.asyncio
async def test_save_upload_limited():
    
    test_file = "test_upload_limit.bin"
    class MockUploadFile:
        def __init__(self):
            self.chunks = [b"12345", b"67890", b""]
        async def read(self, size=-1):
            return self.chunks.pop(0)
    
    # Test success
    size = await save_upload_limited(MockUploadFile(), test_file, 20)
    assert size == 10
    assert os.path.exists(test_file)
    os.remove(test_file)
    
    # Test exceed
    with pytest.raises(HTTPException) as exc_info:
        await save_upload_limited(MockUploadFile(), test_file, 5)
    assert exc_info.value.status_code == 413
    if os.path.exists(test_file):
        os.remove(test_file)

def test_rate_limit():
    from unittest.mock import MagicMock
    mock_request = MagicMock()
    mock_request.client.host = "127.0.0.1"
    
    # Reset limit for tests
    from state import _rate_buckets
    _rate_buckets.clear()
    
    enforce_rate_limit(mock_request, "test_action", 2, 60)
    enforce_rate_limit(mock_request, "test_action", 2, 60)
    
    with pytest.raises(HTTPException) as exc_info:
        enforce_rate_limit(mock_request, "test_action", 2, 60)
    assert exc_info.value.status_code == 429


def test_admin_upload_limit_is_separate_from_regular_upload_limit(monkeypatch):
    import state

    monkeypatch.setattr(state, "require_admin_user", lambda authorization: "admin-user")
    assert state.upload_limit_for("Bearer admin-token") == state.MAX_ADMIN_UPLOAD_BYTES
    assert state.synth_limit_for(state.MAX_ADMIN_UPLOAD_BYTES) == state.MAX_ADMIN_SYNTH_CHARS

    def reject_non_admin(authorization):
        raise HTTPException(status_code=403, detail="관리자만 접근할 수 있습니다.")

    monkeypatch.setattr(state, "require_admin_user", reject_non_admin)
    assert state.upload_limit_for("Bearer regular-token") == state.MAX_UPLOAD_BYTES
    assert state.synth_limit_for(state.MAX_UPLOAD_BYTES) == state.MAX_SYNTH_CHARS
