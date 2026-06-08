import bcrypt

from app.models.user import User
from app.repositories import user_repository

from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.token_blacklist import TokenBlacklist
from app.repositories import token_repository
from app.services.jwt_service import JWTService, TokenType
import uuid


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


async def get_user_profile(db: AsyncSession, user_id: str) -> User:
    user = await user_repository.get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


async def update_user(db: AsyncSession, user: User, update_data: dict) -> User:
    if update_data.get("username") is not None:
        existing = await user_repository.get_user_by_username(db, update_data["username"])
        if existing and existing.id != user.id:
            raise HTTPException(status_code=400, detail="Username already exists")
        user.username = update_data["username"]

    if update_data.get("email") is not None:
        existing = await user_repository.get_user_by_email(db, update_data["email"])
        if existing and existing.id != user.id:
            raise HTTPException(status_code=400, detail="Email already exists")
        user.email = update_data["email"]

    if update_data.get("password") is not None:
        user.hashed_password = hash_password(update_data["password"])
        user.is_verified = True

    if update_data.get("timezone") is not None:
        user.timezone = update_data["timezone"]

    return await user_repository.update_user(db, user)


async def delete_user(db: AsyncSession, user: User) -> User:
    if user.deleted_at is not None:
        raise HTTPException(status_code=400, detail="Account is already deactivated")

    user.deleted_at = datetime.now(timezone.utc)
    user.is_active = False

    return await user_repository.soft_delete_user(db, user)


async def create_user_with_password(
    db: AsyncSession,
    email: str,
    username: str,
    password: str | None = None,
    timezone: str | None = None,
) -> User:
    existing = await user_repository.get_user_by_email(db, email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    existing = await user_repository.get_user_by_username(db, username)
    if existing:
        raise HTTPException(status_code=400, detail="Username already registered")

    hashed_password = hash_password(password) if password else None

    user = User(
        email=email,
        username=username,
        hashed_password=hashed_password,
        is_verified=bool(hashed_password),
        is_active=True,
        timezone=timezone or "Asia/Karachi",
    )

    return await user_repository.create_user(db, user)


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User:
    user = await user_repository.get_user_by_email(db, email)
    if user is None or user.hashed_password is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="User is inactive")

    return user


async def get_or_create_user_google(
    db: AsyncSession,
    email: str,
    google_id: str,
    name: str | None = None,
    gmail_access_token: str | None = None,
    gmail_refresh_token: str | None = None,
    gmail_token_expiry=None,
    timezone: str | None = None,
) -> User:
    import uuid

    user = await user_repository.get_user_by_email(db, email)

    if user:
        if user.google_id is None:
            user.google_id = google_id
        if gmail_access_token:
            user.gmail_access_token = gmail_access_token
        if gmail_refresh_token:
            user.gmail_refresh_token = gmail_refresh_token
        if gmail_token_expiry:
            user.gmail_token_expiry = gmail_token_expiry
        if timezone and user.timezone == "UTC":
            user.timezone = timezone
        await user_repository.update_user(db, user)
        return user

    user = User(
        email=email,
        username=name,
        google_id=google_id,
        is_verified=True,
        is_active=True,
        id=uuid.uuid4(),
        gmail_access_token=gmail_access_token,
        gmail_refresh_token=gmail_refresh_token,
        gmail_token_expiry=gmail_token_expiry,
        timezone=timezone or "Asia/Karachi",
    )
    return await user_repository.create_user(db, user)





async def blacklist_access_token(db: AsyncSession, token: str, reason: str = "logout") -> None:
    payload = JWTService.decode_token(token)
    if not payload or not payload.get("jti"):
        return

    jti = payload["jti"]
    token_type = payload.get("type", TokenType.ACCESS)
    exp = payload.get("exp")
    user_id_str = payload.get("sub")

    expires_at = datetime.fromtimestamp(exp, tz=timezone.utc) if exp else datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    entry = TokenBlacklist(
        token_jti=jti,
        token_type=token_type,
        reason=reason,
        expires_at=expires_at,
        user_id=uuid.UUID(user_id_str) if user_id_str else uuid.uuid4(),
    )

    await token_repository.blacklist_token(db, entry)

