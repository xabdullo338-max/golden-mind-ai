from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")
ALGORITHM = "HS256"

def _secret() -> str:
    secret = os.getenv("GMAI_JWT_SECRET")
    if not secret:
        raise RuntimeError("GMAI_JWT_SECRET is not configured")
    return secret

def create_access_token(subject: str, scopes: list[str], minutes: int = 30) -> str:
    now = datetime.now(UTC)
    payload = {"sub": subject, "scopes": scopes, "iat": now, "exp": now + timedelta(minutes=minutes)}
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM)

def require_token(token: Annotated[str, Depends(oauth2_scheme)]) -> dict:
    exc = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Invalid or expired token",
                        headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, _secret(), algorithms=[ALGORITHM])
    except InvalidTokenError as e:
        raise exc from e
    if not payload.get("sub"):
        raise exc
    return payload
