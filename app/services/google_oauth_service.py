import base64
import json
from typing import Any

import httpx
from pydantic import BaseModel

from app.core.config import settings


class GoogleUserInfo(BaseModel):
    id: str
    email: str
    name: str | None = None


class GoogleOAuthService:
    def __init__(self):
        self.client_id = settings.GOOGLE_CLIENT_ID
        self.client_secret = settings.GOOGLE_CLIENT_SECRET
        self.redirect_uri = settings.GOOGLE_REDIRECT_URI
        self.scopes = [
            "openid",
            "email",
            "profile",
            "https://www.googleapis.com/auth/gmail.readonly",
        ]

    def get_authorization_url(self, state: str | None = None) -> str:
        import secrets
        from urllib.parse import urlencode

        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.scopes),
            "access_type": "offline",
            "prompt": "consent",
        }
        if state:
            params["state"] = state
        return f"{settings.GOOGLE_AUTH_URL}?{urlencode(params)}"

    async def get_timezone_from_ip(self, ip_address: str) -> str | None:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"http://ip-api.com/json/{ip_address}")
                if response.status_code == 200:
                    data = response.json()
                    return data.get("timezone")
        except Exception:
            pass
        return None

    async def exchange_code_for_token(self, code: str) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                settings.GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uri": self.redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            if response.status_code != 200:
                raise ValueError(f"Token exchange failed: {response.text}")
            return response.json()

    async def get_user_info(self, access_token: str) -> GoogleUserInfo:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                settings.GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if response.status_code != 200:
                raise ValueError(f"Failed to get user info: {response.text}")
            data = response.json()
            return GoogleUserInfo(
                id=data["sub"],
                email=data["email"],
                name=data.get("name"),
            )


google_oauth = GoogleOAuthService()