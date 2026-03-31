"""
JWT token creation and decoding with UTC-aware datetimes.
Every token contains: sub, role, jti, exp, iat, token_type.
"""
import uuid
from datetime import datetime, timedelta, timezone

from jose import jwt, JWTError
from fastapi import HTTPException, status

from app.core.config import settings


def create_access_token(data: dict) -> str:
    """
    Create a JWT access token.
    ``data`` must include at least ``sub`` and ``token_type``.
    ``role`` is added from data if present.
    """
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
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
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )