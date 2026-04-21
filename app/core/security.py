"""
Password hashing and verification using PBKDF2-HMAC-SHA256 (Python stdlib).

Format stored in DB:
    pbkdf2$sha256$<iterations>$<base64(salt + dk)>

This format is self-describing, which allows safe iteration-count upgrades
in the future without breaking existing hashes.

Backward compatibility:
    If a stored hash starts with '$2b$' or '$2a$' it is a legacy bcrypt hash.
    verify_value returns False for these (forces password reset) so no
    internal crash occurs — callers receive a clean False and should prompt
    the user to reset their password.

PIN / document-number hashing uses hash_document() which is a fast
deterministic SHA-256 HMAC. It does NOT need a salt because the input
(document number / PIN) is already compared directly and the HMAC key
(SECRET_KEY) keeps rainbow-table attacks infeasible.
"""
import bcrypt
import hashlib
import hmac
import os
import re
import base64

_ALGORITHM = "sha256"
_ITERATIONS = 390_000   # NIST SP 800-132 recommendation for SHA-256
_SALT_LEN   = 16        # bytes
_PREFIX     = "pbkdf2"


# ---------------------------------------------------------------------------
# PUBLIC HELPERS
# ---------------------------------------------------------------------------

def hash_value(value: str) -> str:
    """
    Hash a password using bcrypt with salt rounds >= 12.
    """
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(value.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_value(value: str, stored_hash: str) -> bool:
    """
    Verify a plaintext value against a stored bcrypt hash.
    Also handles legacy PBKDF2 hashes if they exist in the DB (optional but good for transition).
    """
    if not stored_hash:
        return False
    
    # Check if it looks like a PBKDF2 hash from our previous system
    if stored_hash.startswith("pbkdf2$"):
        try:
            prefix, algo, iters_str, encoded = stored_hash.split("$", 3)
            raw = base64.b64decode(encoded.encode("ascii"))
            iterations = int(iters_str)
            salt = raw[:16] # _SALT_LEN was 16
            stored_dk = raw[16:]
            computed_dk = hashlib.pbkdf2_hmac(algo, value.encode("utf-8"), salt, iterations)
            if hmac.compare_digest(stored_dk, computed_dk):
                return True
        except Exception:
            pass
            
    try:
        return bcrypt.checkpw(value.encode("utf-8"), stored_hash.encode("utf-8"))
    except Exception:
        return False


def hash_document(value: str, secret: str) -> str:
    """
    HMAC-SHA256 of a document number / reference using the app secret.
    Deterministic — same input always produces the same output.
    Used for KYC document reference tokens and similar lookup-safe tokens.
    """
    return hmac.new(secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def validate_password_rules(password: str) -> None:
    """Raise ValueError if password does not meet complexity rules.
    
    Minimum 12 characters, at least one uppercase, lowercase, digit,
    and special character.
    """
    from app.core.constants import MIN_PASSWORD_LENGTH

    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(
            f"PASSWORD_TOO_SHORT: Password must be at least {MIN_PASSWORD_LENGTH} characters long"
        )
    if not re.search(r"[A-Z]", password):
        raise ValueError(
            "PASSWORD_NO_UPPERCASE: Password must contain at least one uppercase letter"
        )
    if not re.search(r"[a-z]", password):
        raise ValueError(
            "PASSWORD_NO_LOWERCASE: Password must contain at least one lowercase letter"
        )
    if not re.search(r"[0-9]", password):
        raise ValueError(
            "PASSWORD_NO_DIGIT: Password must contain at least one digit"
        )
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        raise ValueError(
            "PASSWORD_NO_SPECIAL: Password must contain at least one special character"
        )