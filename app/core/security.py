import bcrypt
import re

def hash_value(value: str) -> str:
    value_bytes = value.encode('utf-8')
    if len(value_bytes) > 72:
        value_bytes = value_bytes[:72]
    # bcrypt.hashpw expects bytes, returns bytes
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(value_bytes, salt).decode('utf-8')

def verify_value(value: str, hashed: str) -> bool:
    value_bytes = value.encode('utf-8')
    if len(value_bytes) > 72:
        value_bytes = value_bytes[:72]
    hashed_bytes = hashed.encode('utf-8')
    return bcrypt.checkpw(value_bytes, hashed_bytes)

def validate_password_rules(password: str):
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long")

    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one uppercase letter")

    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain at least one lowercase letter")

    if not re.search(r"[0-9]", password):
        raise ValueError("Password must contain at least one digit")

    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        raise ValueError("Password must contain at least one special character")