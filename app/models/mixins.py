from datetime import datetime
from typing import Optional
import uuid
from sqlalchemy import DateTime, Column
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

class AuditMixin:
    """
    Standard Audit Mixin for SQLAlchemy models.
    Supports both Mapped-style and traditional Column-style (via __table_args__ or manual addition).
    """
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    updated_by = Column(UUID(as_uuid=True), nullable=True)
