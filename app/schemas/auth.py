from pydantic import BaseModel, EmailStr, field_validator
import pytz


class UserCreate(BaseModel):
    email: EmailStr
    username: str
    password: str | None = None
    timezone: str | None = None

    @field_validator("username")
    @classmethod
    def username_min_length(cls, v: str) -> str:
        if len(v) < 3:
            raise ValueError("Username must be at least 3 characters")
        return v

    @field_validator("timezone")
    @classmethod
    def timezone_valid(cls, v: str | None) -> str | None:
        if v is not None and v not in pytz.all_timezones:
            raise ValueError(f"Invalid timezone: {v}. Use IANA format (e.g., 'Asia/Karachi')")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshTokenRequest(BaseModel):
    refresh_token: str
