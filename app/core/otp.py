"""
OTP generation and verification using Python stdlib only.

  • generate_otp()   — cryptographically secure 6-digit OTP via secrets
  • hash_otp()       — HMAC-SHA256(SECRET_KEY, otp) → hex digest stored in DB
  • verify_otp()     — constant-time comparison of recomputed HMAC vs stored
  • get_expiry_time() — UTC datetime 10 minutes from now

No external dependencies: replaces cryptography.Fernet with stdlib hmac + hashlib.
"""
import secrets
import hmac
import hashlib
from datetime import datetime, timedelta, timezone

from app.core.config import settings


def generate_otp() -> str:
    """Return a cryptographically secure 6-digit OTP string."""
    return str(secrets.randbelow(900_000) + 100_000)


def hash_otp(otp: str) -> str:
    """HMAC-SHA256 the OTP with the application SECRET_KEY."""
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        otp.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_otp(input_otp: str, stored_hash: str) -> bool:
    """
    Recompute HMAC for input_otp and compare against stored_hash
    using hmac.compare_digest to prevent timing attacks.
    Returns False on any error (never raises).
    """
    try:
        expected = hmac.new(
            settings.SECRET_KEY.encode("utf-8"),
            input_otp.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, stored_hash)
    except Exception:
        return False


def get_expiry_time() -> datetime:
    """Return a timezone-aware UTC datetime 10 minutes from now."""
    return datetime.now(timezone.utc) + timedelta(minutes=10)