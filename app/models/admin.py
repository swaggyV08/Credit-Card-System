import uuid
from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy import Enum as SQLEnum
from app.db.base_class import Base


from app.models.enums import Suffix

class Admin(Base):
    __tablename__ = "admins"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    first_name = Column(String(100), nullable=False, server_default="System")
    last_name = Column(String(100), nullable=False, server_default="Admin")
    suffix = Column(SQLEnum(Suffix, native_enum=False), nullable=True)

    email = Column(String(255), unique=True, nullable=False)
    country_code = Column(String(10), nullable=True)
    phone_number = Column(String(20), nullable=True)

    password_hash = Column(String, nullable=False)

    position = Column(String(100), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())