import secrets
from datetime import datetime, timedelta,timezone
from cryptography.fernet import Fernet
from app.core.config import settings

fernet = Fernet(settings.FERNET_SECRET_KEY.encode())


def generate_otp() -> str:
    # cryptographically secure 6-digit OTP
    return str(secrets.randbelow(900000) + 100000)


def hash_otp(otp: str) -> str:
    return fernet.encrypt(otp.encode()).decode()


def verify_otp(input_otp: str, stored_hash: str) -> bool:
    try:
        decrypted = fernet.decrypt(stored_hash.encode()).decode()
        return decrypted == input_otp
    except Exception:
        return False


def get_expiry_time():
    return datetime.now(timezone.utc) + timedelta(minutes=10)