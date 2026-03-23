from typing import Any, Dict, List, Optional
from fastapi import HTTPException, status

class BankGradeException(HTTPException):
    """
    Base exception for all bank-grade errors.
    Standardized response format:
    {
        "error": {
            "code": "ZBANQ-XX.X-XXX",
            "message": "Human readable message",
            "details": {},
            "reference_id": "UUID or trace ID"
        }
    }
    """
    def __init__(
        self, 
        status_code: int, 
        code: str, 
        message: str, 
        details: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ):
        super().__init__(status_code=status_code, detail=message, headers=headers)
        self.code = code
        self.message = message
        self.details = details or {}

class ResourceNotFoundException(BankGradeException):
    def __init__(self, resource: str, identifier: Any):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            code="ZBANQ-40.4-001",
            message=f"{resource} not found",
            details={"resource": resource, "identifier": str(identifier)}
        )

class BusinessRuleViolationException(BankGradeException):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="ZBANQ-40.0-100",
            message=message,
            details=details
        )

class ValidationErrorException(BankGradeException):
    def __init__(self, errors: List[Dict[str, Any]]):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="ZBANQ-42.2-001",
            message="Input validation failed",
            details={"errors": errors}
        )
