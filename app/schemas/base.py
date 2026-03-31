"""
Global response schemas used by every endpoint.
"""
import uuid
from datetime import datetime, timezone
from typing import Generic, TypeVar, Optional, Literal

from pydantic import BaseModel, Field, ConfigDict

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str
    message: str
    field: Optional[str] = None


class MetaSchema(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    api_version: str = "1.0.0"


class ResponseEnvelope(BaseModel, Generic[T]):
    status: Literal["success", "error"]
    data: Optional[T] = None
    meta: MetaSchema = Field(default_factory=MetaSchema)
    errors: list[ErrorDetail] = []


class AuditMixin(BaseModel):
    created_at: Optional[datetime] = None
    created_by: Optional[uuid.UUID] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[uuid.UUID] = None


class PaginationSchema(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_previous: bool


# ── Helper functions for building responses ───────────────────────

def envelope_success(data, meta: Optional[MetaSchema] = None) -> dict:
    """Build a success envelope dict."""
    return {
        "status": "success",
        "data": data,
        "meta": (meta or MetaSchema()).model_dump(),
        "errors": [],
    }


def envelope_error(
    errors: list[ErrorDetail],
    meta: Optional[MetaSchema] = None,
) -> dict:
    """Build an error envelope dict."""
    return {
        "status": "error",
        "data": None,
        "meta": (meta or MetaSchema()).model_dump(),
        "errors": [e.model_dump() for e in errors],
    }


def build_pagination(total: int, page: int, page_size: int) -> dict:
    """Calculate pagination metadata."""
    total_pages = max(1, (total + page_size - 1) // page_size)
    return PaginationSchema(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_previous=page > 1,
    ).model_dump()
