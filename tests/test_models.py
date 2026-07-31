from datetime import datetime
from models import (
    UserRegister, UserLogin, UserResponse, TokenResponse,
    AudiobookMetadata, PlaybackState, AudiobookUpload,
    UserDB, AudiobookDB, PlaybackHistoryDB
)

def test_user_models():
    ur = UserRegister(email="test@test.com", password="pwd", full_name="Test")
    assert ur.email == "test@test.com"
    
    ul = UserLogin(email="test@test.com", password="pwd")
    assert ul.password == "pwd"
    
    now = datetime.now()
    ur_resp = UserResponse(id="1", email="test@test.com", full_name=None, avatar_url=None, created_at=now)
    assert ur_resp.id == "1"
    
    tr = TokenResponse(access_token="tok", user=ur_resp)
    assert tr.token_type == "bearer"

def test_audiobook_models():
    now = datetime.now()
    am = AudiobookMetadata(id="1", title="title", duration_seconds=10, created_at=now)
    assert am.id == "1"
    
    ps = PlaybackState(audiobook_id="1", current_time_seconds=10, last_played_at=now)
    assert ps.playback_speed == 1.0
    
    au = AudiobookUpload(title="t", file_name="f")
    assert au.title == "t"

def test_db_models():
    now = datetime.now()
    udb = UserDB(id="1", email="a@a.com", password_hash="hash", created_at=now, updated_at=now)
    assert udb.id == "1"
    
    adb = AudiobookDB(id="1", user_id="u1", title="t", file_name="f", created_at=now, storage_path="path")
    assert adb.storage_path == "path"
    
    pdb = PlaybackHistoryDB(id="1", user_id="u1", audiobook_id="a1", last_played_at=now, updated_at=now)
    assert pdb.repeat_mode == "off"
