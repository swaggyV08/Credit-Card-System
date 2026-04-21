"""
Job Logging System — Track execution of background jobs
Table: job_logs
"""
import uuid
from datetime import datetime, timezone, date
from sqlalchemy import String, DateTime, JSON, Date, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.db.base_class import Base

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

def _new_uuid() -> uuid.UUID:
    return uuid.uuid4()

class JobLog(Base):
    __tablename__ = "job_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    job_name: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    job_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PROCESSING") # PROCESSING, COMPLETED, FAILED
    
    cycle_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    
    # Metadata for summary/results
    # { "accounts_attempted": 50, "accounts_succeeded": 48... "results": [...] }
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<JobLog {self.job_name} status={self.status}>"
