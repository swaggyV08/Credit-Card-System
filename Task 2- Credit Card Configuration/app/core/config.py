from pydantic_settings import BaseSettings
from pydantic import ConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://postgres:Rasenshuriken%401@localhost:5432/credit_card_db"

    SECRET_KEY: str = "supersecretkey"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    OTP_EXPIRY_MINUTES: int = 3
    FERNET_SECRET_KEY: str
    FIRST_ADMIN_EMAIL: str = "vishnup@email.com"
    FIRST_ADMIN_PASSCODE: str = "260304"
    FIRST_ADMIN_PASSWORD: str = "Rasenshuriken@1"
    FIRST_ADMIN_NAME: str = "Vishnu P"
    FIRST_ADMIN_CONTACT: str = "+917019666370"

    model_config = ConfigDict(env_file=".env")


settings = Settings()