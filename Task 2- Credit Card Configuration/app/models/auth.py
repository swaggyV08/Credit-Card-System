import uuid
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base_class import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    email = Column(String, unique=True, index=True, nullable=False)
    country_code = Column(String, nullable=False)
    phone_number = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    is_cif_completed = Column(Boolean,default=False)
    is_kyc_completed = Column(Boolean,default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    auth_credential = relationship(
        "AuthCredential",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan"
    )

    customer_profile = relationship(
        "CustomerProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan"
    )


class AuthCredential(Base):
    __tablename__ = "auth_credentials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True)

    password_hash = Column(String, nullable=False)
    passcode_hash = Column(String, nullable=False)

    password_updated_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="auth_credential")


