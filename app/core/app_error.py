"""
Structured application-level errors for business rule violations.

Used by the service layer to raise domain errors that get automatically
translated to ResponseEnvelope format by the global exception handler.
"""
from fastapi import HTTPException


class AppError(HTTPException):
    """
    Base class for all business-logic errors.

    Attributes:
        code: Machine-readable code (e.g. CIF_INCOMPLETE, KYC_INCOMPLETE)
        message: Human-readable explanation
        http_status: HTTP status code (default 422)
    """

    def __init__(
        self,
        code: str,
        message: str,
        http_status: int = 422,
        context: dict | None = None,
    ):
        detail = {
            "code": code,
            "message": message,
        }
        if context:
            detail["context"] = context
        super().__init__(
            status_code=http_status,
            detail=detail,
        )
        self.code = code
        self.message = message
        self.context = context

class RefactoredException(Exception):
    def __init__(self, error_code: str, message: str, status_code: int = 400):
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
