import os
import pytest
from unittest.mock import patch, MagicMock
from auth import (
    create_access_token, decode_token,
    get_supabase_client
)
from datetime import timedelta


def test_jwt_requires_secret_key(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_access_token({"sub": "user-1"})


def test_default_token_lifetime_is_one_year():
    import auth

    assert auth.DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES == 525_600

def test_jwt_tokens():
    data = {"sub": "user123"}
    # Test creation with default expire
    token1 = create_access_token(data)
    decoded1 = decode_token(token1)
    assert decoded1 is not None
    assert decoded1["sub"] == "user123"
    
    # Test creation with custom expire
    token2 = create_access_token(data, expires_delta=timedelta(minutes=5))
    decoded2 = decode_token(token2)
    assert decoded2 is not None
    
    # Test invalid token
    assert decode_token("invalid.token.string") is None
    
    # Test missing sub
    token_no_sub = create_access_token({"other": "data"})
    assert decode_token(token_no_sub) is None

@patch.dict(os.environ, {"SUPABASE_URL": "http://test.supabase", "SUPABASE_KEY": "testkey", "SUPABASE_SERVICE_ROLE_KEY": "servicekey"})
def test_get_supabase_client_success():
    with patch("supabase.create_client") as mock_create:
        mock_create.return_value = MagicMock()
        
        # Anon key
        client1 = get_supabase_client(use_service_role=False)
        assert client1 is not None
        mock_create.assert_called_with("http://test.supabase", "testkey")
        
        # Service key
        client2 = get_supabase_client(use_service_role=True)
        assert client2 is not None
        mock_create.assert_called_with("http://test.supabase", "servicekey")

@patch.dict(os.environ, {"SUPABASE_URL": "http://test.supabase", "SUPABASE_KEY": "testkey"}, clear=True)
def test_get_supabase_client_no_service_key():
    with patch("supabase.create_client") as mock_create:
        mock_create.return_value = MagicMock()
        # Fallback to anon key if service key missing
        client = get_supabase_client(use_service_role=True)
        assert client is not None
        mock_create.assert_called_with("http://test.supabase", "testkey")

@patch.dict(os.environ, {}, clear=True)
def test_get_supabase_client_missing_url():
    client = get_supabase_client()
    assert client is None

@patch.dict(os.environ, {"SUPABASE_URL": "http://test.supabase"}, clear=True)
def test_get_supabase_client_missing_key():
    client = get_supabase_client()
    assert client is None

# removed kakao tests


@patch.dict(os.environ, {"SUPABASE_URL": "http://test.supabase", "SUPABASE_KEY": "testkey"})
def test_get_supabase_client_is_reused():
    """create_client()는 호출마다 새 httpx 세션을 연다. _supabase_or_503()
    호출 지점이 49곳이라 요청마다 여러 개가 생기고 있었다."""
    with patch("supabase.create_client") as mock_create:
        mock_create.return_value = MagicMock()

        first = get_supabase_client()
        second = get_supabase_client()

        assert first is second
        assert mock_create.call_count == 1


@patch.dict(os.environ, {"SUPABASE_URL": "http://test.supabase", "SUPABASE_KEY": "testkey"})
def test_failed_supabase_client_is_not_cached():
    """부팅 직후의 일시적 실패를 기억해버리면 그 뒤로 영영 DB에 못 붙는다."""
    with patch("supabase.create_client") as mock_create:
        mock_create.side_effect = RuntimeError("boom")
        assert get_supabase_client() is None

        mock_create.side_effect = None
        mock_create.return_value = MagicMock()
        assert get_supabase_client() is not None
