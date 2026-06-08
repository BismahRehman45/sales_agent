from datetime import datetime, timedelta
from typing import Any
import uuid
import secrets

from jose import jwt, JWTError

from app.core.config import settings


class TokenType:
    ACCESS = "access"
    REFRESH = "refresh"


def create_jti() -> str:
    return secrets.token_urlsafe(32)


class JWTService:
    @staticmethod
    def create_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> tuple[str, str]:
        jti = create_jti()
        to_encode = data.copy()
        to_encode.update({"jti": jti, "exp": datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))})
        token = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        return token, jti

    @staticmethod
    def create_access_token(user_id: uuid.UUID | str) -> tuple[str, str]:
        user_id_str = str(user_id) if isinstance(user_id, uuid.UUID) else user_id
        token, jti = JWTService.create_token(
            {"sub": user_id_str, "type": TokenType.ACCESS},
            timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        return token, jti

    @staticmethod
    def create_refresh_token(user_id: uuid.UUID | str) -> tuple[str, str]:
        user_id_str = str(user_id) if isinstance(user_id, uuid.UUID) else user_id
        token, jti = JWTService.create_token(
            {"sub": user_id_str, "type": TokenType.REFRESH},
            timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        )
        return token, jti

    @staticmethod
    def decode_token(token: str) -> dict[str, Any] | None:
        try:
            return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        except JWTError:
            return None

    @staticmethod
    def verify_token(token: str, expected_type: str) -> dict[str, Any] | None:
        payload = JWTService.decode_token(token)
        if not payload:
            return None
        if payload.get("type") != expected_type:
            return None
        return payload