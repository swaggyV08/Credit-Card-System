from sqlalchemy import Column, String, DateTime
from sqlalchemy.sql import func
from app.db.base_class import Base

class BlacklistedToken(Base):
    """
    Stores JWT JTI (JWT ID) claims that have been explicitly revoked, 
    e.g., when a user is blocked due to compliance hits.
    """
    __tablename__ = "token_blacklist"

    jti = Column(String(50), primary_key=True, index=True)
    blacklisted_at = Column(DateTime(timezone=True), server_default=func.now())
