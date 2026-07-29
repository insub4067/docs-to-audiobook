"""Database models and schemas for P2 features."""

from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

# ============================================================
# Request/Response Schemas
# ============================================================

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: str
    email: str
    full_name: Optional[str]
    avatar_url: Optional[str]
    created_at: datetime

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

class AudiobookMetadata(BaseModel):
    id: str
    title: str
    duration_seconds: int
    created_at: datetime

class PlaybackState(BaseModel):
    audiobook_id: str
    current_time_seconds: int
    playback_speed: float = 1.0
    repeat_mode: str = "off"
    last_played_at: datetime

class AudiobookUpload(BaseModel):
    title: str
    file_name: str

# ============================================================
# Database Models (for SQLAlchemy ORM - optional for future)
# ============================================================

class UserDB(BaseModel):
    """User model for database"""
    id: str
    email: str
    full_name: Optional[str] = None
    password_hash: str
    google_id: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class AudiobookDB(BaseModel):
    """Audiobook model for database"""
    id: str
    user_id: str
    title: str
    file_name: str
    duration_seconds: Optional[int] = None
    created_at: datetime
    storage_path: str

    class Config:
        from_attributes = True

class PlaybackHistoryDB(BaseModel):
    """Playback history model for database"""
    id: str
    user_id: str
    audiobook_id: str
    current_time_seconds: int = 0
    playback_speed: float = 1.0
    repeat_mode: str = "off"
    last_played_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
