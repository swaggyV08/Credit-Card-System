import uuid
from sqlalchemy import Column, String, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func
from app.db.base_class import Base

class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    action_type = Column(String, nullable=False)
    actor_type = Column(String, nullable=False) # SYSTEM, ADMIN, USER
    actor_id = Column(UUID(as_uuid=True), nullable=True)
    resource_id = Column(UUID(as_uuid=True), nullable=True) # e.g., application_id
    previous_state = Column(JSONB, nullable=True)
    new_state = Column(JSONB, nullable=True)
    metadata_fields = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
