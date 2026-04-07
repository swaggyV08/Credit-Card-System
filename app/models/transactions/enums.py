"""
Transaction Processing System — Enumerations
All enums for the transaction lifecycle, disputes, settlements, and controls.
"""
from enum import Enum


# =====================================================
# TRANSACTION ENUMS
# =====================================================
class TransactionType(str, Enum):
    """Primary transaction classification."""
    PURCHASE = "PURCHASE"
    CASH_ADVANCE = "CASH_ADVANCE"
    BALANCE_TRANSFER = "BALANCE_TRANSFER"
    QUASI_CASH = "QUASI_CASH"
    REFUND = "REFUND"
    PRE_AUTH = "PRE_AUTH"
    FEE = "FEE"
    INTEREST_CHARGE = "INTEREST_CHARGE"
    PAYMENT = "PAYMENT"
    FEE_WAIVER = "FEE_WAIVER"


class TransactionStatus(str, Enum):
    """Transaction lifecycle states."""
    PENDING_AUTHORIZATION = "PENDING_AUTHORIZATION"
    AUTHORIZED = "AUTHORIZED"
    CLEARED = "CLEARED"
    SETTLED = "SETTLED"
    REVERSED = "REVERSED"
    VOIDED = "VOIDED"
    DECLINED = "DECLINED"
    DISPUTED = "DISPUTED"
    CHARGED_BACK = "CHARGED_BACK"
    DISPUTE_REJECTED = "DISPUTE_REJECTED"
    FORCE_POST = "FORCE_POST"
    BLOCKED = "BLOCKED"


class POSEntryMode(str, Enum):
    """Point-of-sale entry method."""
    CHIP = "CHIP"
    SWIPE = "SWIPE"
    NFC = "NFC"
    MANUAL = "MANUAL"


class RiskTier(str, Enum):
    """Fraud risk classification."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# =====================================================
# HOLD ENUMS
# =====================================================
class HoldStatus(str, Enum):
    """Credit hold lifecycle states."""
    ACTIVE = "ACTIVE"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"


# =====================================================
# CLEARING & SETTLEMENT ENUMS
# =====================================================
class ClearingBatchStatus(str, Enum):
    """Clearing batch processing states."""
    RECEIVED = "RECEIVED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class SettlementRunStatus(str, Enum):
    """Settlement run states."""
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    PARTIAL_FAILURE = "PARTIAL_FAILURE"
    FAILED = "FAILED"


class NetworkType(str, Enum):
    """Card network providers."""
    VISA = "VISA"
    MASTERCARD = "MASTERCARD"
    AMEX = "AMEX"
    RUPAY = "RUPAY"


# =====================================================
# DISPUTE ENUMS
# =====================================================
class DisputeType(str, Enum):
    """Dispute reason classification."""
    UNAUTHORIZED = "UNAUTHORIZED"
    DUPLICATE_CHARGE = "DUPLICATE_CHARGE"
    GOODS_NOT_RECEIVED = "GOODS_NOT_RECEIVED"
    QUALITY_ISSUE = "QUALITY_ISSUE"
    PROCESSING_ERROR = "PROCESSING_ERROR"
    SUBSCRIPTION_CANCEL = "SUBSCRIPTION_CANCEL"
    FRAUD = "FRAUD"


class DisputeStatus(str, Enum):
    """Dispute lifecycle states."""
    OPENED = "OPENED"
    UNDER_REVIEW = "UNDER_REVIEW"
    RESOLVED_WON = "RESOLVED_WON"
    RESOLVED_LOST = "RESOLVED_LOST"
    ESCALATED = "ESCALATED"
    WITHDRAWN = "WITHDRAWN"


class ProvisionalCreditStatus(str, Enum):
    """Provisional credit states."""
    PROVISIONAL = "PROVISIONAL"
    PERMANENT = "PERMANENT"
    REVERSED = "REVERSED"


# =====================================================
# FEE ENUMS
# =====================================================
class FeeType(str, Enum):
    """Fee classification."""
    ANNUAL_FEE = "ANNUAL_FEE"
    LATE_PAYMENT_FEE = "LATE_PAYMENT_FEE"
    OVER_LIMIT_FEE = "OVER_LIMIT_FEE"
    CASH_ADVANCE_FEE = "CASH_ADVANCE_FEE"
    FOREIGN_TRANSACTION_FEE = "FOREIGN_TRANSACTION_FEE"
    RETURNED_PAYMENT_FEE = "RETURNED_PAYMENT_FEE"
    CARD_REPLACEMENT_FEE = "CARD_REPLACEMENT_FEE"
    INTEREST_CHARGE = "INTEREST_CHARGE"
    OVERLIMIT_FEE = "OVERLIMIT_FEE"


# =====================================================
# PAYMENT ENUMS
# =====================================================
class PaymentStatus(str, Enum):
    """Payment lifecycle states."""
    PENDING = "PENDING"
    POSTED = "POSTED"
    REVERSED = "REVERSED"
    FAILED = "FAILED"


class PaymentSource(str, Enum):
    """Payment source channel."""
    BANK_ACCOUNT = "BANK_ACCOUNT"
    BANK_TRANSFER = "BANK_TRANSFER"
    NEFT = "NEFT"
    RTGS = "RTGS"
    UPI = "UPI"
    CHEQUE = "CHEQUE"


# =====================================================
# STATEMENT ENUMS
# =====================================================
class StatementStatus(str, Enum):
    """Statement lifecycle states."""
    OPEN = "OPEN"
    BILLED = "BILLED"
    PAID = "PAID"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    OVERDUE = "OVERDUE"
    WAIVED = "WAIVED"


class LineItemType(str, Enum):
    """Statement line item classification."""
    PURCHASE = "PURCHASE"
    CASH_ADVANCE = "CASH_ADVANCE"
    REFUND = "REFUND"
    PAYMENT = "PAYMENT"
    FEE = "FEE"
    INTEREST = "INTEREST"
    INTEREST_CHARGE = "INTEREST_CHARGE"
    CREDIT = "CREDIT"
    ADJUSTMENT = "ADJUSTMENT"


class ExportFormat(str, Enum):
    """Statement export format."""
    PDF = "PDF"
    CSV = "CSV"


class ExportStatus(str, Enum):
    """Export job status."""
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# =====================================================
# RISK ALERT ENUMS
# =====================================================
class RiskAlertStatus(str, Enum):
    """Risk alert workflow states."""
    OPEN = "OPEN"
    REVIEWED = "REVIEWED"
    ESCALATED = "ESCALATED"
    DISMISSED = "DISMISSED"


class ReviewOutcome(str, Enum):
    """Risk alert review outcomes."""
    TRUE_POSITIVE = "TRUE_POSITIVE"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    INCONCLUSIVE = "INCONCLUSIVE"


# =====================================================
# AUDIT ENUMS
# =====================================================
class AuditAction(str, Enum):
    """Audit log action types."""
    TRANSACTION_CREATED = "TRANSACTION_CREATED"
    TRANSACTION_AUTHORIZED = "TRANSACTION_AUTHORIZED"
    TRANSACTION_REVERSED = "TRANSACTION_REVERSED"
    TRANSACTION_VOIDED = "TRANSACTION_VOIDED"
    TRANSACTION_FLAGGED = "TRANSACTION_FLAGGED"
    TRANSACTION_UNFLAGGED = "TRANSACTION_UNFLAGGED"
    TRANSACTION_CAPTURED = "TRANSACTION_CAPTURED"
    HOLD_CREATED = "HOLD_CREATED"
    HOLD_RELEASED = "HOLD_RELEASED"
    HOLD_EXPIRED = "HOLD_EXPIRED"
    CLEARING_BATCH_PROCESSED = "CLEARING_BATCH_PROCESSED"
    SETTLEMENT_COMPLETED = "SETTLEMENT_COMPLETED"
    DISPUTE_OPENED = "DISPUTE_OPENED"
    DISPUTE_RESOLVED = "DISPUTE_RESOLVED"
    DISPUTE_ESCALATED = "DISPUTE_ESCALATED"
    DISPUTE_WITHDRAWN = "DISPUTE_WITHDRAWN"
    REFUND_POSTED = "REFUND_POSTED"
    FEE_APPLIED = "FEE_APPLIED"
    FEE_WAIVED = "FEE_WAIVED"
    PAYMENT_POSTED = "PAYMENT_POSTED"
    PAYMENT_REVERSED = "PAYMENT_REVERSED"
    CONTROLS_UPDATED = "CONTROLS_UPDATED"
    RISK_ALERT_REVIEWED = "RISK_ALERT_REVIEWED"
    RISK_ALERT_DISMISSED = "RISK_ALERT_DISMISSED"
    RISK_ALERT_ESCALATED = "RISK_ALERT_ESCALATED"


# =====================================================
# RECONCILIATION ENUMS
# =====================================================
class ReconciliationExceptionType(str, Enum):
    """Reconciliation exception classification."""
    FORCE_POST = "FORCE_POST"
    DUPLICATE = "DUPLICATE"
    EXPIRED_AUTH = "EXPIRED_AUTH"
    AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
    UNMATCHED_CLEARING = "UNMATCHED_CLEARING"
