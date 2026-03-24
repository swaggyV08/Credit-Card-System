"""
Response Envelope — Standardized API response wrapper.
All transaction system endpoints return responses in this format:
{
  "status": "success" | "error",
  "data": <payload>,
  "meta": { "request_id": str, "timestamp": str, "version": "v1" },
  "errors": [ { "code": str, "message": str, "field": str|null } ]
}
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str
    message: str
    field: str | None = None


class ResponseMeta(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    version: str = "v1"


class PaginationMeta(BaseModel):
    total: int
    pages: int
    current_page: int
    has_next: bool
    page_size: int


class ResponseEnvelope(BaseModel):
    """Standard response wrapper used by all transaction system endpoints."""
    status: str = "success"
    data: Any = None
    meta: ResponseMeta = Field(default_factory=ResponseMeta)
    errors: list[ErrorDetail] = Field(default_factory=list)


def success_response(data: Any, **meta_overrides) -> dict:
    """Build a success response envelope."""
    meta = ResponseMeta(**meta_overrides) if meta_overrides else ResponseMeta()
    return {
        "status": "success",
        "data": data,
        "meta": meta.model_dump(),
        "errors": [],
    }


def error_response(code: str, message: str, field: str | None = None, status_code: int = 400) -> dict:
    """Build an error response envelope (used with HTTPException)."""
    return {
        "status": "error",
        "data": None,
        "meta": ResponseMeta().model_dump(),
        "errors": [{"code": code, "message": message, "field": field}],
    }


def paginated_response(data: list, total: int, page: int, page_size: int) -> dict:
    """Build a paginated success response envelope."""
    pages = (total + page_size - 1) // page_size if page_size > 0 else 0
    return {
        "status": "success",
        "data": data,
        "meta": ResponseMeta().model_dump(),
        "pagination": {
            "total": total,
            "pages": pages,
            "current_page": page,
            "has_next": page < pages,
            "page_size": page_size,
        },
        "errors": [],
    }
