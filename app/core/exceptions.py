"""
Domain Exception Classes — Week 5

All business-rule exceptions inherit from AppError so they are caught
by the global exception handler in main.py and rendered using the
ResponseEnvelope format.
"""
from typing import Any, Dict, List, Optional
from fastapi import HTTPException, status
from app.core.app_error import AppError


# ─── Legacy bank-grade exceptions (kept for backward compatibility) ──

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


# ═══════════════════════════════════════════════════════
# Domain-specific exceptions (Week 5)
# All inherit from AppError for envelope-format handling
# ═══════════════════════════════════════════════════════

class InsufficientFundsError(AppError):
    """Raised when payment or transaction exceeds available credit."""
    def __init__(self, available: Any, requested: Any):
        super().__init__(
            code="INSUFFICIENT_FUNDS",
            message=f"Insufficient funds. Available: {available}, Requested: {requested}",
            http_status=402,
        )


class DuplicateTransactionError(AppError):
    """Raised when an idempotency key collision is detected."""
    def __init__(self, idempotency_key: str):
        super().__init__(
            code="DUPLICATE_TRANSACTION",
            message=f"Duplicate transaction detected for idempotency key: {idempotency_key}",
            http_status=409,
        )


class FraudDeclinedError(AppError):
    """Raised when a transaction is hard-declined by the fraud engine."""
    def __init__(self, rule: str, detail: str = ""):
        super().__init__(
            code="FRAUD_DECLINED",
            message=f"Transaction declined by fraud rule [{rule}]. {detail}".strip(),
            http_status=403,
        )


class StatementNotFoundError(AppError):
    """Raised when a billing statement cannot be located."""
    def __init__(self, identifier: Any):
        super().__init__(
            code="STATEMENT_NOT_FOUND",
            message=f"Statement not found: {identifier}",
            http_status=404,
        )


class PaymentNotFoundError(AppError):
    """Raised when a payment record cannot be located."""
    def __init__(self, identifier: Any):
        super().__init__(
            code="PAYMENT_NOT_FOUND",
            message=f"Payment not found: {identifier}",
            http_status=404,
        )


class AccountNotActiveError(AppError):
    """Raised when an operation targets a non-active credit account."""
    def __init__(self, account_id: Any, current_status: str = "UNKNOWN"):
        super().__init__(
            code="ACCOUNT_NOT_ACTIVE",
            message=f"Credit account {account_id} is not active (status: {current_status})",
            http_status=403,
        )


class CardNotActiveError(AppError):
    """Raised when an operation targets a non-active card."""
    def __init__(self, card_id: Any, current_status: str = "UNKNOWN"):
        super().__init__(
            code="CARD_NOT_ACTIVE",
            message=f"Card {card_id} is not active (status: {current_status})",
            http_status=403,
        )


class BillingCycleError(AppError):
    """Raised for billing generation issues (e.g. already generated)."""
    def __init__(self, message: str):
        super().__init__(
            code="BILLING_CYCLE_ERROR",
            message=message,
            http_status=400,
        )


class IdempotencyConflictError(AppError):
    """Raised when storing an idempotency key that already exists."""
    def __init__(self, key: str):
        super().__init__(
            code="IDEMPOTENCY_CONFLICT",
            message=f"Idempotency key already used: {key}",
            http_status=409,
        )


class MissingIdempotencyKeyError(AppError):
    def __init__(self):
        super().__init__(
            code="MISSING_IDEMPOTENCY_KEY",
            message="Idempotency-Key header is required for this operation.",
            http_status=422,
        )


class InvalidIdempotencyKeyError(AppError):
    def __init__(self):
        super().__init__(
            code="INVALID_IDEMPOTENCY_KEY",
            message="Idempotency-Key must be a valid UUID v4.",
            http_status=422,
        )


class VelocityExceededError(AppError):
    def __init__(self, retry_after: int = 60):
        super().__init__(
            code="VELOCITY_EXCEEDED",
            message="Transaction velocity limits exceeded. Please wait before trying again.",
            http_status=429,
        )
        self.retry_after = retry_after


class InvalidSettlementDateError(AppError):
    def __init__(self):
        super().__init__(
            code="INVALID_SETTLEMENT_DATE",
            message="Settlement date cannot be in the future.",
            http_status=400,
        )


class InvalidNetworkError(AppError):
    def __init__(self):
        super().__init__(
            code="INVALID_NETWORK",
            message="Invalid network. Supported: VISA, MASTERCARD, AMEX, RUPAY.",
            http_status=422,
        )


class SettlementAlreadyRunError(AppError):
    def __init__(self):
        super().__init__(
            code="SETTLEMENT_ALREADY_RUN",
            message="Settlement has already been run for this date and network.",
            http_status=409,
        )


class DisputeAlreadyExistsError(AppError):
    def __init__(self):
        super().__init__(
            code="DISPUTE_ALREADY_EXISTS",
            message="An active dispute already exists for this transaction.",
            http_status=409,
        )


class TransactionNotDisputableError(AppError):
    def __init__(self, status: str):
        super().__init__(
            code="TRANSACTION_NOT_DISPUTABLE",
            message=f"Transaction in status '{status}' cannot be disputed. Must be SETTLED or CLEARED.",
            http_status=400,
        )


class DisputeWindowExpiredError(AppError):
    def __init__(self):
        super().__init__(
            code="DISPUTE_WINDOW_EXPIRED",
            message="Dispute window (120 days) has expired for this transaction.",
            http_status=400,
        )


class EvidenceDeadlinePassedError(AppError):
    def __init__(self):
        super().__init__(
            code="EVIDENCE_DEADLINE_PASSED",
            message="Evidence submission deadline has passed for this dispute.",
            http_status=400,
        )


class ResolutionRequiredError(AppError):
    def __init__(self):
        super().__init__(
            code="RESOLUTION_REQUIRED",
            message="The 'resolution' field (WON/LOST) is mandatory for the 'resolve' command.",
            http_status=422,
        )


class InvalidMonthError(AppError):
    def __init__(self):
        super().__init__(
            code="INVALID_MONTH",
            message="Month must be an integer between 1 and 12.",
            http_status=422,
        )


class WaiverReasonTooShortError(AppError):
    def __init__(self):
        super().__init__(
            code="WAIVER_REASON_TOO_SHORT",
            message="Waiver reason must be at least 10 characters long.",
            http_status=422,
        )


class FeeAlreadyWaivedError(AppError):
    def __init__(self):
        super().__init__(
            code="FEE_ALREADY_WAIVED",
            message="This fee has already been waived.",
            http_status=409,
        )


class FeeNotFoundError(AppError):
    def __init__(self, fee_id: Any):
        super().__init__(
            code="FEE_NOT_FOUND",
            message=f"Fee not found or already waived: {fee_id}",
            http_status=404,
        )


class InvalidPaymentAmountError(AppError):
    def __init__(self):
        super().__init__(
            code="INVALID_PAYMENT_AMOUNT",
            message="Payment amount must be greater than zero.",
            http_status=400,
        )


class PaymentExceedsBalanceError(AppError):
    def __init__(self, balance: Any):
        super().__init__(
            code="PAYMENT_EXCEEDS_BALANCE",
            message=f"Payment exceeds the outstanding balance ({balance}).",
            http_status=400,
        )


class AdminOnlyControlError(AppError):
    def __init__(self):
        super().__init__(
            code="ADMIN_ONLY_CONTROL",
            message="Limit and restriction controls can only be updated by administrators.",
            http_status=403,
        )


class InvalidMccCodeError(AppError):
    def __init__(self):
        super().__init__(
            code="INVALID_MCC_CODE",
            message="MCC code must be exactly 4 digits.",
            http_status=422,
        )


class InvalidCountryCodeError(AppError):
    def __init__(self):
        super().__init__(
            code="INVALID_COUNTRY_CODE",
            message="Country code must be ISO 3166-1 alpha-2 (2 uppercase letters).",
            http_status=422,
        )


class TransactionNotRefundableError(AppError):
    def __init__(self, status: str):
        super().__init__(
            code="TRANSACTION_NOT_REFUNDABLE",
            message=f"Refunds can only be issued against SETTLED transactions. Current status: {status}",
            http_status=400,
        )


class RefundExceedsTransactionError(AppError):
    def __init__(self):
        super().__init__(
            code="REFUND_EXCEEDS_TRANSACTION",
            message="Refund amount cannot exceed the original transaction amount.",
            http_status=400,
        )


class InvalidRefundAmountError(AppError):
    def __init__(self):
        super().__init__(
            code="INVALID_REFUND_AMOUNT",
            message="Refund amount must be greater than zero.",
            http_status=400,
        )


class AlreadyFullyRefundedError(AppError):
    def __init__(self):
        super().__init__(
            code="ALREADY_REFUNDED",
            message="This transaction has already been fully refunded.",
            http_status=409,
        )
