from pydantic import BaseModel, EmailStr, field_validator
import uuid
from datetime import datetime
import pytz


class UserUpdate(BaseModel):
    username: str | None = None
    email: EmailStr | None = None
    password: str | None = None
    timezone: str | None = None

    @field_validator("username")
    @classmethod
    def username_min_length(cls, v: str | None) -> str | None:
        if v is not None and len(v) < 3:
            raise ValueError("Username must be at least 3 characters")
        return v

    @field_validator("timezone")
    @classmethod
    def timezone_valid(cls, v: str | None) -> str | None:
        if v is not None and v not in pytz.all_timezones:
            raise ValueError(f"Invalid timezone: {v}. Use IANA format (e.g., 'Asia/Karachi')")
        return v


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    username: str
    is_active: bool
    is_verified: bool
    timezone: str
    created_at: datetime
    deleted_at: datetime | None = None

    model_config = {"from_attributes": True}


class DeleteResponse(BaseModel):
    message: str
    deleted: bool = True
