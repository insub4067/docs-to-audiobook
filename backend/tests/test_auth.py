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
        # 실제 구글 ID 토큰에는 항상 들어 있다. 이게 True가 아니면 거부한다.
        "email_verified": True,
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


def _google_profile(**overrides):
    profile = {
        "sub": "1234567890",
        "email": "test@example.com",
        "email_verified": True,
        "name": "Test User",
    }
    profile.update(overrides)
    return profile


@pytest.mark.parametrize("profile,reason", [
    (_google_profile(email_verified=False), "검증되지 않은 이메일"),
    (_google_profile(email_verified=None), "email_verified 누락"),
    (_google_profile(email=None), "이메일 누락"),
    (_google_profile(sub=None), "sub 누락"),
])
def test_verify_google_rejects_unusable_profiles(profile, reason):
    """_upsert_social_user가 이메일로 기존 계정을 찾아 연결하기 때문에,
    검증되지 않은 이메일을 믿으면 남의 이메일로 만든 계정으로 그 사람의
    서재에 들어갈 수 있다. sub/email이 없으면 계정을 특정할 수도 없다."""
    with patch('google.oauth2.id_token.verify_oauth2_token', return_value=profile):
        with pytest.raises(HTTPException) as exc_info:
            _verify_google("token")
    assert exc_info.value.status_code == 401, reason
