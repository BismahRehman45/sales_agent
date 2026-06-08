from typing import Annotated
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.repositories import token_repository, user_repository
from app.services.jwt_service import JWTService, TokenType
import uuid

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)
http_bearer = HTTPBearer(auto_error=False, description="Paste raw JWT (no 'Bearer ' prefix)")


async def get_current_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    oauth_token: Annotated[str | None, Depends(oauth2_scheme)] = None,
    bearer: Annotated[HTTPAuthorizationCredentials | None, Depends(http_bearer)] = None,
) -> User:
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token_revoked_exception = HTTPException(
        status_code=401,
        detail="Token has been revoked",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = oauth_token or (bearer.credentials if bearer else None)
    if token is None:
        raise credentials_exception

    payload = JWTService.verify_token(token, TokenType.ACCESS)
    if payload is None:
        raise credentials_exception

    jti = payload.get("jti")
    if jti and await token_repository.is_token_blacklisted(db, jti):
        raise token_revoked_exception

    user_id_str = payload.get("sub")
    if user_id_str is None:
        raise credentials_exception

    try:
        user_uuid = uuid.UUID(user_id_str)
    except ValueError:
        raise credentials_exception

    user = await user_repository.get_user_by_id(db, user_uuid)

    if user is None or user.deleted_at is not None:
        raise credentials_exception

    return user
