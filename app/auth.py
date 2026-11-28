from __future__ import annotations

import hmac
import os
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError

from .users import UserStore

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")


def _secret() -> str:
    value = os.getenv("GMAI_JWT_SECRET", "").strip()
    if not value:
        raise RuntimeError("GMAI_JWT_SECRET is not configured")
    return value


def create_access_token(subject: str, scopes: list[str], minutes: int = 30) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": subject,
            "scopes": scopes,
            "iat": now,
            "exp": now + timedelta(minutes=minutes),
        },
        _secret(),
        algorithm="HS256",
    )


def role_scopes(role: str) -> list[str]:
    return {
        "admin": ["read", "trade", "admin"],
        "trader": ["read", "trade"],
        "viewer": ["read"],
    }.get(role, [])


def current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> dict:
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
    )
    try:
        payload = jwt.decode(token, _secret(), algorithms=["HS256"])
    except InvalidTokenError as e:
        raise exc from e
    if not payload.get("sub"):
        raise exc
    return payload



def decode_access_token(token: str) -> dict:
    payload = jwt.decode(token, _secret(), algorithms=["HS256"])
    if not payload.get("sub"):
        raise InvalidTokenError("missing subject")
    return payload

def require_scope(scope: str):
    def dependency(user: Annotated[dict, Depends(current_user)]) -> dict:
        if scope not in user.get("scopes", []):
            raise HTTPException(status_code=403, detail=f"Missing scope: {scope}")
        return user

    return dependency


def authenticate(username: str, password: str) -> dict | None:
    # Vercel instances are ephemeral and may be recreated between requests.
    # Use the deployment environment for the primary admin account instead of
    # relying on a mutable SQLite file for authentication.
    env_username = os.getenv("GMAI_ADMIN_USERNAME", "").strip()
    env_password = os.getenv("GMAI_ADMIN_PASSWORD", "")
    if env_username and env_password:
        if hmac.compare_digest(username.strip(), env_username) and hmac.compare_digest(
            password, env_password
        ):
            return {
                "username": env_username,
                "role": "admin",
                "disabled": False,
            }

    if os.getenv("VERCEL") != "1":
        return UserStore().authenticate(username, password)
    return None
