import os
import pytest
from unittest.mock import patch, MagicMock
from auth import (
    hash_password, verify_password,
    create_access_token, decode_token,
    get_supabase_client
)
from datetime import timedelta

def test_password_hashing():
    pwd = "my_secure_password"
    hashed = hash_password(pwd)
    assert hashed != pwd
    assert verify_password(pwd, hashed) is True
    assert verify_password("wrong", hashed) is False

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
