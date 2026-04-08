"""
JWT token creation and decoding with UTC-aware datetimes.
Every token contains: sub, role, jti, exp, iat, token_type.

Uses PyJWT (stdlib-aligned) — compliant with the mandated tech stack.
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import HTTPException, status

from app.core.config import settings


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.

    ``data`` must include at least ``sub`` and ``token_type``.
    ``role`` is added from data if present.

    Token expiry rules:
    - If ``expires_delta`` is explicitly provided, use it.
    - If ``role`` is USER: 1 hour expiry.
    - If ``role`` is SUPERADMIN/ADMIN/MANAGER/SALES: 8 hours expiry.
    - Fallback: uses ACCESS_TOKEN_EXPIRE_MINUTES from settings.
    """
    to_encode = data.copy()
    now = datetime.now(timezone.utc)

    if expires_delta is not None:
        expire = now + expires_delta
    else:
        role = to_encode.get("role", "USER").upper()
        if role in ("SUPERADMIN", "ADMIN", "MANAGER", "SALES"):
            expire = now + timedelta(hours=8)
        elif role == "USER":
            expire = now + timedelta(hours=1)
        else:
            expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({
        "exp": expire,
        "iat": now,
        "jti": str(uuid.uuid4()),
    })
    # Ensure role is always in the token
    if "role" not in to_encode:
        to_encode["role"] = to_encode.get("type", "USER")
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT. Raises HTTP 401 on failure."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "TOKEN_EXPIRED", "message": "Token has expired"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TOKEN", "message": "Invalid or expired token"},
        )