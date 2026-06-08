"""
Gmail Token Service

Handles OAuth2 token refresh and expiry checks for Gmail integration.
"""

import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User
from app.repositories import user_repository

logger = logging.getLogger(__name__)


async def ensure_token_fresh(db: AsyncSession, user: User) -> User:
    """
    Ensure Gmail access token is valid. Refresh if expired.

    Returns:
        Updated User object with valid token
    """
    if not user.gmail_refresh_token:
        logger.warning(f"User {user.id} has no refresh token")
        return user

    # Check if token needs refresh (5-minute buffer)
    if user.gmail_token_expiry:
        buffer = timedelta(minutes=5)
        if datetime.now(timezone.utc) < (user.gmail_token_expiry - buffer):
            # Token is still valid
            return user

    logger.info(f"Refreshing Gmail token for user {user.id}")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                settings.GOOGLE_TOKEN_URL,
                data={
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "refresh_token": user.gmail_refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            response.raise_for_status()
            token_data = response.json()

            # Update user with new token
            user.gmail_access_token = token_data.get("access_token")
            expires_in = token_data.get("expires_in", 3600)
            user.gmail_token_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

            # Persist to database
            user = await user_repository.update_user(db, user)
            logger.info(f"Successfully refreshed Gmail token for user {user.id}")

            return user

    except Exception as e:
        logger.error(f"Error refreshing Gmail token for user {user.id}: {str(e)}")
        return user
