import uuid
from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy import Enum as SQLEnum
from app.db.base_class import Base

from app.core.roles import Role


class Admin(Base):
    __tablename__ = "admins"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    full_name = Column(String(200), nullable=False, server_default="System Admin")

    email = Column(String(255), unique=True, nullable=False)
    country_code = Column(String(10), nullable=True)
    phone_number = Column(String(20), nullable=True)

    password_hash = Column(String, nullable=False)

    role = Column(SQLEnum(Role, native_enum=False), nullable=False, server_default=Role.MANAGER.value)
    department = Column(String(100), nullable=True)
    employee_id = Column(String(50), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())