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
        *,
        code: str,
        message: str,
        http_status: int = 422,
    ):
        super().__init__(
            status_code=http_status,
            detail={
                "code": code,
                "message": message,
            },
        )
        self.code = code
        self.message = message
