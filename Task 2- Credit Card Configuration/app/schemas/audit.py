from typing import Optional, Dict, Any
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime

class AuditLogCreate(BaseModel):
    action_type: str
    actor_type: str
    actor_id: Optional[UUID] = None
    resource_id: Optional[UUID] = None
    previous_state: Optional[Dict[str, Any]] = None
    new_state: Optional[Dict[str, Any]] = None
    metadata_fields: Optional[Dict[str, Any]] = None

class AuditLogResponse(AuditLogCreate):
    id: UUID
    created_at: datetime
    class Config:
        from_attributes = True
