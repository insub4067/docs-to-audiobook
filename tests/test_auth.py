import pytest
from fastapi import HTTPException
from unittest.mock import patch
from routes.auth_social import _verify_google

def test_verify_google_invalid_token():
    # If the token is invalid, google.oauth2.id_token.verify_oauth2_token raises ValueError
    # which we catch and raise HTTPException(401)
    
    with patch('google.oauth2.id_token.verify_oauth2_token') as mock_verify:
        mock_verify.side_effect = ValueError("Invalid token")
        
        with pytest.raises(HTTPException) as exc_info:
            _verify_google("fake_token")
            
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "유효하지 않은 토큰입니다."

def test_verify_google_valid_token():
    # If the token is valid, it returns the decoded profile dict
    mock_profile = {
        "sub": "1234567890",
        "email": "test@example.com",
        "name": "Test User",
        "picture": "http://example.com/pic.jpg"
    }
    
    with patch('google.oauth2.id_token.verify_oauth2_token') as mock_verify:
        mock_verify.return_value = mock_profile
        
        result = _verify_google("valid_token")
        
        assert result["provider"] == "google"
        assert result["provider_id"] == "1234567890"
        assert result["email"] == "test@example.com"
        assert result["full_name"] == "Test User"
        assert result["avatar_url"] == "http://example.com/pic.jpg"
