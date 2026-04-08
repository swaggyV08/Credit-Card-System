"""
Pydantic response_model schemas for Swagger UI.

Every endpoint from Authentication through Billing uses these schemas
to display concrete, realistic example response bodies in Swagger.
"""
from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List, Any
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


# =====================================================
# ENVELOPE WRAPPER
# =====================================================
class MetaResponse(BaseModel):
    request_id: str = Field(..., json_schema_extra={"example": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"})
    timestamp: str = Field(..., json_schema_extra={"example": "2026-04-08T10:30:00.000000+00:00"})
    api_version: str = Field(..., json_schema_extra={"example": "1.0.0"})


class ErrorDetailResponse(BaseModel):
    code: str
    message: str
    field: Optional[str] = None


# =====================================================
# AUTH — REGISTRATION
# =====================================================
class RegistrationData(BaseModel):
    """Registration success response data."""
    user_id: str = Field(..., json_schema_extra={"example": "ZNBNQ000001"})
    message: str = Field(..., json_schema_extra={"example": "Verify with OTP"})

class RegistrationResponse(BaseModel):
    """Full envelope response for user registration."""
    status: str = Field(..., json_schema_extra={"example": "success"})
    data: RegistrationData
    meta: MetaResponse
    errors: List[ErrorDetailResponse] = []

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "status": "success",
            "data": {
                "user_id": "ZNBNQ000001",
                "message": "Verify with OTP"
            },
            "meta": {
                "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "timestamp": "2026-04-08T10:30:00.000000+00:00",
                "api_version": "1.0.0"
            },
            "errors": []
        }
    })


# =====================================================
# AUTH — LOGIN (USER)
# =====================================================
class UserLoginData(BaseModel):
    """Login response data for USER role."""
    access_token: str = Field(..., json_schema_extra={"example": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."})
    token_type: str = Field(..., json_schema_extra={"example": "bearer"})
    role: str = Field(..., json_schema_extra={"example": "USER"})
    user_id: str = Field(..., json_schema_extra={"example": "ZNBNQ000001"})
    message: str = Field(..., json_schema_extra={"example": "Welcome Vishnu Prasad"})
    is_cif_completed: bool = Field(..., json_schema_extra={"example": True})
    is_kyc_completed: bool = Field(..., json_schema_extra={"example": True})
    application_status: str = Field(..., json_schema_extra={"example": "APPROVED"})
    credit_account_id: Optional[str] = Field(None, json_schema_extra={"example": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"})
    login_timestamp_utc: str = Field(..., json_schema_extra={"example": "2026-04-08T10:30:00+00:00"})
    login_timestamp_local: str = Field(..., json_schema_extra={"example": "2026-04-08T16:00:00"})

class UserLoginResponse(BaseModel):
    """Full envelope response for user login."""
    status: str = Field(..., json_schema_extra={"example": "success"})
    data: UserLoginData
    meta: MetaResponse
    errors: List[ErrorDetailResponse] = []

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "status": "success",
            "data": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "role": "USER",
                "user_id": "ZNBNQ000001",
                "message": "Welcome Vishnu Prasad",
                "is_cif_completed": True,
                "is_kyc_completed": True,
                "application_status": "APPROVED",
                "credit_account_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "login_timestamp_utc": "2026-04-08T10:30:00+00:00",
                "login_timestamp_local": "2026-04-08T16:00:00"
            },
            "meta": {
                "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "timestamp": "2026-04-08T10:30:00.000000+00:00",
                "api_version": "1.0.0"
            },
            "errors": []
        }
    })


# =====================================================
# AUTH — LOGIN (ADMIN)
# =====================================================
class AdminLoginData(BaseModel):
    """Login response data for admin roles."""
    access_token: str = Field(..., json_schema_extra={"example": "eyJhbGciOiJIUzI1NiJ9..."})
    token_type: str = Field(..., json_schema_extra={"example": "bearer"})
    role: str = Field(..., json_schema_extra={"example": "ADMIN"})
    employee_id: Optional[str] = Field(None, json_schema_extra={"example": "ZNBAD000001"})
    message: str = Field(..., json_schema_extra={"example": "Welcome ADMIN: Rajesh Kumar"})
    login_timestamp_utc: str = Field(..., json_schema_extra={"example": "2026-04-08T10:30:00+00:00"})
    login_timestamp_local: str = Field(..., json_schema_extra={"example": "2026-04-08T16:00:00"})

class AdminLoginResponse(BaseModel):
    """Full envelope response for admin login."""
    status: str = Field(..., json_schema_extra={"example": "success"})
    data: AdminLoginData
    meta: MetaResponse
    errors: List[ErrorDetailResponse] = []

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "status": "success",
            "data": {
                "access_token": "eyJhbGciOiJIUzI1NiJ9...",
                "token_type": "bearer",
                "role": "ADMIN",
                "employee_id": "ZNBAD000001",
                "message": "Welcome ADMIN: Rajesh Kumar",
                "login_timestamp_utc": "2026-04-08T10:30:00+00:00",
                "login_timestamp_local": "2026-04-08T16:00:00"
            },
            "meta": {
                "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "timestamp": "2026-04-08T10:30:00.000000+00:00",
                "api_version": "1.0.0"
            },
            "errors": []
        }
    })


# =====================================================
# AUTH — PASSWORD RESET
# =====================================================
class PasswordResetData(BaseModel):
    message: str = Field(..., json_schema_extra={"example": "Password updated successfully"})

class PasswordResetResponse(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "success"})
    data: PasswordResetData
    meta: MetaResponse
    errors: List[ErrorDetailResponse] = []


# =====================================================
# AUTH — OTP
# =====================================================
class OTPGenerateData(BaseModel):
    message: str = Field(..., json_schema_extra={"example": "OTP dispatched"})

class OTPVerifyData(BaseModel):
    message: str = Field(..., json_schema_extra={"example": "REGISTRATION COMPLETE"})
    user_id: Optional[str] = Field(None, json_schema_extra={"example": "f47ac10b-58cc-4372-a5"})
    password_reset_token: Optional[str] = None

class OTPResponse(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "success"})
    data: OTPVerifyData
    meta: MetaResponse
    errors: List[ErrorDetailResponse] = []

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "status": "success",
            "data": {
                "message": "REGISTRATION COMPLETE",
                "user_id": "f47ac10b-58cc-4372-a5",
                "password_reset_token": None
            },
            "meta": {
                "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "timestamp": "2026-04-08T10:30:00.000000+00:00",
                "api_version": "1.0.0"
            },
            "errors": []
        }
    })


# =====================================================
# AUTH — ADD ADMIN
# =====================================================
class AddAdminData(BaseModel):
    admin_id: str = Field(..., json_schema_extra={"example": "3fa85f64-5717-4562-b3fc-2c963f66afa6"})
    admin: str = Field(..., json_schema_extra={"example": "Rajesh Kumar added successfully"})
    created_at: str = Field(..., json_schema_extra={"example": "2026-04-08T10:30:00.000000+00:00"})
    created_by: str = Field(..., json_schema_extra={"example": "12345678-1234-1234-1234-1234567890ab"})

class AddAdminResponse(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "success"})
    data: AddAdminData
    meta: MetaResponse
    errors: List[ErrorDetailResponse] = []


# =====================================================
# CUSTOMER CIF
# =====================================================
class CIFStageData(BaseModel):
    message: str = Field(..., json_schema_extra={"example": "Personal details saved"})

class CIFStageResponse(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "success"})
    data: CIFStageData
    meta: MetaResponse
    errors: List[ErrorDetailResponse] = []


class CIFSubmitData(BaseModel):
    message: str = Field(..., json_schema_extra={"example": "CIF Submitted Successfully"})
    user_id: str = Field(..., json_schema_extra={"example": "ZBNQ00000001"})
    access_token: str = Field(..., json_schema_extra={"example": "eyJhbGciOiJIUzI1NiJ9..."})

class CIFSubmitResponse(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "success"})
    data: CIFSubmitData
    meta: MetaResponse
    errors: List[ErrorDetailResponse] = []


class KYCUploadData(BaseModel):
    message: str = Field(..., json_schema_extra={"example": "KYC SUBMITTED"})
    submission_id: str = Field(..., json_schema_extra={"example": "3fa85f64-5717-4562-b3fc-2c963f66afa6"})
    storage: str = Field(..., json_schema_extra={"example": "server_fs"})
    path: str = Field(..., json_schema_extra={"example": "uploads/kyc/ZBNQ00000001_PAN_1712568600.pdf"})

class KYCUploadResponse(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "success"})
    data: KYCUploadData
    meta: MetaResponse
    errors: List[ErrorDetailResponse] = []


# =====================================================
# APPLICATIONS
# =====================================================
class ApplicationSubmitData(BaseModel):
    message: str = Field(..., json_schema_extra={"example": "Application submitted successfully and passed initial eligibility checks."})
    application_id: str = Field(..., json_schema_extra={"example": "3fa85f64-5717-4562-b3fc-2c963f66afa6"})
    status: str = Field(..., json_schema_extra={"example": "SUBMITTED"})

class ApplicationSubmitResponse(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "success"})
    data: ApplicationSubmitData
    meta: MetaResponse
    errors: List[ErrorDetailResponse] = []


class ApplicationListData(BaseModel):
    items: List[Any] = Field(..., json_schema_extra={"example": []})
    total: int = Field(..., json_schema_extra={"example": 15})
    page: int = Field(..., json_schema_extra={"example": 1})
    page_size: int = Field(..., json_schema_extra={"example": 20})

class ApplicationListResponse(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "success"})
    data: ApplicationListData
    meta: MetaResponse
    errors: List[ErrorDetailResponse] = []


# =====================================================
# CREDIT PRODUCTS
# =====================================================
class CreditProductCreateData(BaseModel):
    id: str = Field(..., json_schema_extra={"example": "3fa85f64-5717-4562-b3fc-2c963f66afa6"})
    product_code: str = Field(..., json_schema_extra={"example": "cp-12345"})
    product_name: str = Field(..., json_schema_extra={"example": "ZBanque Gold Credit Card"})
    product_category: str = Field(..., json_schema_extra={"example": "CARD"})
    status: str = Field(..., json_schema_extra={"example": "DRAFT"})
    created_at: Optional[str] = Field(None, json_schema_extra={"example": "2026-04-08T10:30:00+00:00"})

class CreditProductCreateResponse(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "success"})
    data: CreditProductCreateData
    meta: MetaResponse
    errors: List[ErrorDetailResponse] = []


class CreditProductStatusData(BaseModel):
    message: str = Field(..., json_schema_extra={"example": "Credit Product approved"})
    product_id: str = Field(..., json_schema_extra={"example": "3fa85f64-5717-4562-b3fc-2c963f66afa6"})
    product_code: str = Field(..., json_schema_extra={"example": "cp-12345"})
    product_name: str = Field(..., json_schema_extra={"example": "ZBanque Gold Credit Card"})

class CreditProductStatusResponse(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "success"})
    data: CreditProductStatusData
    meta: MetaResponse
    errors: List[ErrorDetailResponse] = []


class CreditProductDeleteData(BaseModel):
    message: str = Field(..., json_schema_extra={"example": "Credit Product permanently deleted"})
    product_id: str = Field(..., json_schema_extra={"example": "3fa85f64-5717-4562-b3fc-2c963f66afa6"})

class CreditProductDeleteResponse(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "success"})
    data: CreditProductDeleteData
    meta: MetaResponse
    errors: List[ErrorDetailResponse] = []


# =====================================================
# CARD PRODUCTS
# =====================================================
class CardProductCreateData(BaseModel):
    card_product_id: str = Field(..., json_schema_extra={"example": "3fa85f64-5717-4562-b3fc-2c963f66afa6"})
    effective_from: Optional[str] = Field(None, json_schema_extra={"example": "2026-04-08T10:30:00+00:00"})
    effective_to: Optional[str] = Field(None, json_schema_extra={"example": "2027-04-08T10:30:00+00:00"})
    created_at: Optional[str] = Field(None, json_schema_extra={"example": "2026-04-08T10:30:00+00:00"})
    created_by: Optional[str] = Field(None, json_schema_extra={"example": "3fa85f64-5717-4562-b3fc-2c963f66afa6"})

class CardProductCreateResponse(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "success"})
    data: CardProductCreateData
    meta: MetaResponse
    errors: List[ErrorDetailResponse] = []


class CardProductApproveData(BaseModel):
    card_product_id: str = Field(..., json_schema_extra={"example": "3fa85f64-5717-4562-b3fc-2c963f66afa6"})
    credit_product_id: str = Field(..., json_schema_extra={"example": "3fa85f64-5717-4562-b3fc-2c963f66afa6"})
    effective_from: Optional[str] = Field(None, json_schema_extra={"example": "2026-04-08T10:30:00+00:00"})
    effective_to: Optional[str] = Field(None, json_schema_extra={"example": "2027-04-08T10:30:00+00:00"})
    created_at: Optional[str] = Field(None, json_schema_extra={"example": "2026-04-08T10:30:00+00:00"})
    created_by: Optional[str] = Field(None, json_schema_extra={"example": "3fa85f64-5717-4562-b3fc-2c963f66afa6"})
    approved_by: Optional[str] = Field(None, json_schema_extra={"example": "3fa85f64-5717-4562-b3fc-2c963f66afa6"})

class CardProductApproveResponse(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "success"})
    data: CardProductApproveData
    meta: MetaResponse
    errors: List[ErrorDetailResponse] = []


class CardProductDeleteData(BaseModel):
    message: str = Field(..., json_schema_extra={"example": "Card Product permanently deleted"})

class CardProductDeleteResponse(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "success"})
    data: CardProductDeleteData
    meta: MetaResponse
    errors: List[ErrorDetailResponse] = []


# =====================================================
# ADMIN: USER MANAGEMENT
# =====================================================
class UserListItemData(BaseModel):
    user_id: str = Field(..., json_schema_extra={"example": "ZBNQ00000001"})
    credit_account_id: Optional[str] = Field(None, json_schema_extra={"example": "3fa85f64-5717-4562-b3fc-2c963f66afa6"})
    card_id: Optional[str] = Field(None, json_schema_extra={"example": "3fa85f64-5717-4562-b3fc-2c963f66afa6"})
    account_status: Optional[str] = Field(None, json_schema_extra={"example": "ACTIVE"})

class UserListResponse(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "success"})
    data: List[UserListItemData]
    meta: MetaResponse
    errors: List[ErrorDetailResponse] = []


# =====================================================
# CREDIT ACCOUNTS
# =====================================================
class CreditAccountListData(BaseModel):
    page: int = Field(..., json_schema_extra={"example": 1})
    limit: int = Field(..., json_schema_extra={"example": 20})
    total_records: int = Field(..., json_schema_extra={"example": 5})
    accounts: List[Any] = []

class CreditAccountListResponse(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "success"})
    data: CreditAccountListData
    meta: MetaResponse
    errors: List[ErrorDetailResponse] = []


class CreditAccountUpdateData(BaseModel):
    credit_account_id: str = Field(..., json_schema_extra={"example": "3fa85f64-5717-4562-b3fc-2c963f66afa6"})
    old_credit_limit: Optional[str] = Field(None, json_schema_extra={"example": "500000.000"})
    new_credit_limit: Optional[str] = Field(None, json_schema_extra={"example": "750000.000"})
    available_credit: Optional[str] = Field(None, json_schema_extra={"example": "750000.000"})
    updated_by: Optional[str] = Field(None, json_schema_extra={"example": "3fa85f64-5717-4562-b3fc-2c963f66afa6"})
    updated_at: Optional[str] = Field(None, json_schema_extra={"example": "2026-04-08T10:30:00+00:00"})

class CreditAccountUpdateResponse(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "success"})
    data: CreditAccountUpdateData
    meta: MetaResponse
    errors: List[ErrorDetailResponse] = []


# =====================================================
# CARDS — ISSUANCE
# =====================================================
class CardIssueData(BaseModel):
    card_id: str = Field(..., json_schema_extra={"example": "3fa85f64-5717-4562-b3fc-2c963f66afa6"})
    pan_masked: str = Field(..., json_schema_extra={"example": "XXXX-XXXX-XXXX-4321"})
    card_status: str = Field(..., json_schema_extra={"example": "CREATED"})
    expiry_date: str = Field(..., json_schema_extra={"example": "12/29"})
    card_network: Optional[str] = Field(None, json_schema_extra={"example": "VISA"})

class CardIssueResponse(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "success"})
    data: CardIssueData
    meta: MetaResponse
    errors: List[ErrorDetailResponse] = []


# =====================================================
# CARDS — LIFECYCLE
# =====================================================
class CardLifecycleData(BaseModel):
    card_id: str = Field(..., json_schema_extra={"example": "3fa85f64-5717-4562-b3fc-2c963f66afa6"})
    card_status: str = Field(..., json_schema_extra={"example": "ACTIVE"})
    message: Optional[str] = Field(None, json_schema_extra={"example": "Card activated successfully"})

class CardLifecycleResponse(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "success"})
    data: CardLifecycleData
    meta: MetaResponse
    errors: List[ErrorDetailResponse] = []


# =====================================================
# TRANSACTIONS
# =====================================================
class TransactionCreateData(BaseModel):
    transaction_id: str = Field(..., json_schema_extra={"example": "3fa85f64-5717-4562-b3fc-2c963f66afa6"})
    auth_code: Optional[str] = Field(None, json_schema_extra={"example": "AUTH7829"})
    status: str = Field(..., json_schema_extra={"example": "AUTHORIZED"})
    amount: float = Field(..., json_schema_extra={"example": 2500.00})
    currency: str = Field(..., json_schema_extra={"example": "INR"})
    available_credit: float = Field(..., json_schema_extra={"example": 497500.00})
    hold_id: Optional[str] = Field(None, json_schema_extra={"example": "3fa85f64-5717-4562-b3fc-2c963f66afa6"})
    hold_expiry: Optional[str] = Field(None, json_schema_extra={"example": "2026-04-15T10:30:00+00:00"})

class TransactionCreateResponse(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "success"})
    data: TransactionCreateData
    meta: MetaResponse
    errors: List[ErrorDetailResponse] = []

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "status": "success",
            "data": {
                "transaction_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                "auth_code": "AUTH7829",
                "status": "AUTHORIZED",
                "amount": 2500.00,
                "currency": "INR",
                "available_credit": 497500.00,
                "hold_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                "hold_expiry": "2026-04-15T10:30:00+00:00"
            },
            "meta": {
                "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "timestamp": "2026-04-08T10:30:00.000000+00:00",
                "api_version": "1.0.0"
            },
            "errors": []
        }
    })


class TransactionListData(BaseModel):
    data: List[Any] = []
    total_hold_amount: float = Field(..., json_schema_extra={"example": 2500.00})
    available_credit: float = Field(..., json_schema_extra={"example": 497500.00})
    meta: dict = Field(..., json_schema_extra={"example": {"total": 42, "page": 1, "page_size": 20}})

class TransactionListResponse(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "success"})
    data: TransactionListData
    meta: MetaResponse
    errors: List[ErrorDetailResponse] = []


# =====================================================
# DISPUTES
# =====================================================
class DisputeCreateData(BaseModel):
    dispute_id: str = Field(..., json_schema_extra={"example": "3fa85f64-5717-4562-b3fc-2c963f66afa6"})
    case_number: str = Field(..., json_schema_extra={"example": "DSP-2026-0001"})
    status: str = Field(..., json_schema_extra={"example": "OPENED"})
    provisional_credit_issued: bool = Field(..., json_schema_extra={"example": True})
    deadline: str = Field(..., json_schema_extra={"example": "2026-05-08T10:30:00+00:00"})
    next_steps: str = Field(..., json_schema_extra={"example": "Submit supporting documents within 30 days."})

class DisputeCreateResponse(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "success"})
    data: DisputeCreateData
    meta: MetaResponse
    errors: List[ErrorDetailResponse] = []


# =====================================================
# SETTLEMENT
# =====================================================
class SettlementRunData(BaseModel):
    settlement_run_id: str = Field(..., json_schema_extra={"example": "3fa85f64-5717-4562-b3fc-2c963f66afa6"})
    cards_settled: int = Field(..., json_schema_extra={"example": 142})
    total_amount: float = Field(..., json_schema_extra={"example": 1250000.00})
    failed_count: int = Field(..., json_schema_extra={"example": 0})

class SettlementRunResponse(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "success"})
    data: SettlementRunData
    meta: MetaResponse
    errors: List[ErrorDetailResponse] = []

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "status": "success",
            "data": {
                "settlement_run_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                "cards_settled": 142,
                "total_amount": 1250000.00,
                "failed_count": 0
            },
            "meta": {
                "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "timestamp": "2026-04-08T10:30:00.000000+00:00",
                "api_version": "1.0.0"
            },
            "errors": []
        }
    })


# =====================================================
# PAYMENTS
# =====================================================
class PaymentCreateData(BaseModel):
    payment_id: str = Field(..., json_schema_extra={"example": "3fa85f64-5717-4562-b3fc-2c963f66afa6"})
    amount: float = Field(..., json_schema_extra={"example": 15000.00})
    status: str = Field(..., json_schema_extra={"example": "POSTED"})
    allocated_fees: float = Field(..., json_schema_extra={"example": 500.00})
    allocated_interest: float = Field(..., json_schema_extra={"example": 2500.00})
    allocated_cash_advance: float = Field(..., json_schema_extra={"example": 0.00})
    allocated_purchases: float = Field(..., json_schema_extra={"example": 12000.00})

class PaymentCreateResponse(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "success"})
    data: PaymentCreateData
    meta: MetaResponse
    errors: List[ErrorDetailResponse] = []


class PaymentListData(BaseModel):
    data: List[Any] = []
    meta: dict = Field(..., json_schema_extra={"example": {"total": 5, "page": 1, "page_size": 20}})

class PaymentListResponse(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "success"})
    data: PaymentListData
    meta: MetaResponse
    errors: List[ErrorDetailResponse] = []


# =====================================================
# CARD CONTROLS
# =====================================================
class CardControlsData(BaseModel):
    card_id: str = Field(..., json_schema_extra={"example": "3fa85f64-5717-4562-b3fc-2c963f66afa6"})
    daily_limit: Optional[float] = Field(None, json_schema_extra={"example": 50000.00})
    monthly_limit: Optional[float] = Field(None, json_schema_extra={"example": 500000.00})
    online_enabled: bool = Field(..., json_schema_extra={"example": True})
    contactless_enabled: bool = Field(..., json_schema_extra={"example": True})
    atm_enabled: bool = Field(..., json_schema_extra={"example": True})

class CardControlsResponse(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "success"})
    data: CardControlsData
    meta: MetaResponse
    errors: List[ErrorDetailResponse] = []


# =====================================================
# BILLING
# =====================================================
class BillingGenerateData(BaseModel):
    statements_generated: int = Field(..., json_schema_extra={"example": 25})
    cycle_date: str = Field(..., json_schema_extra={"example": "2026-04-01"})
    details: List[Any] = []

class BillingGenerateResponse(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "success"})
    data: BillingGenerateData
    meta: MetaResponse
    errors: List[ErrorDetailResponse] = []


class LateFeeData(BaseModel):
    late_fees_applied: int = Field(..., json_schema_extra={"example": 3})
    details: List[Any] = []

class LateFeeResponse(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "success"})
    data: LateFeeData
    meta: MetaResponse
    errors: List[ErrorDetailResponse] = []


class StatementListData(BaseModel):
    data: List[Any] = []
    meta: dict = Field(..., json_schema_extra={"example": {"total": 12, "page": 1, "page_size": 20}})

class StatementListResponse(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "success"})
    data: StatementListData
    meta: MetaResponse
    errors: List[ErrorDetailResponse] = []


class FraudFlagListData(BaseModel):
    data: List[Any] = []
    meta: dict = Field(..., json_schema_extra={"example": {"total": 2, "page": 1, "page_size": 20}})

class FraudFlagListResponse(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "success"})
    data: FraudFlagListData
    meta: MetaResponse
    errors: List[ErrorDetailResponse] = []


# =====================================================
# GENERIC MESSAGE RESPONSE (reusable)
# =====================================================
class MessageData(BaseModel):
    message: str = Field(..., json_schema_extra={"example": "Operation completed successfully"})

class MessageResponse(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "success"})
    data: MessageData
    meta: MetaResponse
    errors: List[ErrorDetailResponse] = []
