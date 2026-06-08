from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import settings
from app.dependencies.auth import get_current_user, oauth2_scheme
from app.schemas.auth import TokenResponse, UserCreate, RefreshTokenRequest, LoginRequest
from app.schemas.user_schema import UserResponse
from app.services.google_oauth_service import google_oauth
from app.services.jwt_service import JWTService, TokenType
from app.services.user_service import create_user_with_password, authenticate_user, get_or_create_user_google, \
    blacklist_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse)
async def register(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    return await create_user_with_password(
        db,
        email=user_data.email,
        username=user_data.username,
        password=user_data.password,
        timezone=user_data.timezone,
    )


@router.post("/token", response_model=TokenResponse)
async def get_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    user = await authenticate_user(db, form_data.username, form_data.password)

    access_token, _ = JWTService.create_access_token(user.id)
    refresh_token, _ = JWTService.create_refresh_token(user.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    login_data: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    user = await authenticate_user(db, login_data.email, login_data.password)

    access_token, _ = JWTService.create_access_token(user.id)
    refresh_token, _ = JWTService.create_refresh_token(user.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get("/google/login")
async def google_login():
    url = google_oauth.get_authorization_url()
    return {"authorization_url": url}


@router.get("/google/callback")
async def google_callback(code: str, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        token_data = await google_oauth.exchange_code_for_token(code)
        access_token_google = token_data.get("access_token")
        refresh_token_google = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 3600)

        if not access_token_google:
            raise HTTPException(status_code=400, detail="No access token received")

        from datetime import datetime, timedelta, timezone as dt_tz
        token_expiry = datetime.now(dt_tz.utc) + timedelta(seconds=expires_in)

        user_info = await google_oauth.get_user_info(access_token_google)

        # Detect timezone from IP address
        client_ip = request.client.host
        timezone = await google_oauth.get_timezone_from_ip(client_ip)

        user = await get_or_create_user_google(
            db=db,
            email=user_info.email,
            google_id=user_info.id,
            name=user_info.name,
            gmail_access_token=access_token_google,
            gmail_refresh_token=refresh_token_google,
            gmail_token_expiry=token_expiry,
            timezone=timezone,
        )

        access_token, _ = JWTService.create_access_token(user.id)
        refresh_token, _ = JWTService.create_refresh_token(user.id)

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: RefreshTokenRequest):
    payload = JWTService.verify_token(request.refresh_token, TokenType.REFRESH)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    user_id = payload.get("sub")
    access_token, _ = JWTService.create_access_token(user_id)
    refresh_token, _ = JWTService.create_refresh_token(user_id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/logout")
async def logout(
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    if not token:
        raise HTTPException(status_code=401, detail="No token provided")

    payload = JWTService.decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    await blacklist_access_token(db, token, reason="logout")

    return {"message": "Successfully logged out", "revoked": True}
