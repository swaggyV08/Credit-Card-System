from typing import Optional, List, Union
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from app.models.enums import (
    ApplicationStatus, ApplicationStage, AccountStatus, CardStatus, CardType
)

# =====================================================
# CREDIT CARD APPLICATION
# =====================================================
class CreditCardApplicationCreate(BaseModel):
    cif_id: UUID
    credit_product_id: UUID
    card_product_id: UUID
    employment_status: Optional[str] = None
    declared_income: Optional[float] = None

class CreditCardApplicationUpdate(BaseModel):
    application_status: Optional[ApplicationStatus] = None
    current_stage: Optional[ApplicationStage] = None
    rejection_reason_code: Optional[str] = None

class CreditCardApplicationSummary(BaseModel):
    application_id: UUID = Field(validation_alias="id")
    cif_id: Optional[str] = Field(validation_alias="customer_cif_id")
    class Config:
        from_attributes = True
        populate_by_name = True

class CreditCardApplicationResponse(BaseModel):
    id: UUID
    cif_id: Optional[str] = Field(validation_alias="customer_cif_id")
    user_id: UUID
    credit_product_id: UUID
    card_product_id: UUID
    
    application_status: ApplicationStatus
    current_stage: ApplicationStage
    
    employment_status: Optional[str]
    declared_income: Optional[float]
    bureau_score: Optional[int] = None
    risk_band: Optional[str] = None
    
    retry_count: int
    cooling_period_until: Optional[datetime]
    rejection_reason_code: Optional[str]
    rejection_reason: Optional[str]
    credit_account_id: Optional[UUID] = None
    
    submitted_at: datetime
    reviewed_at: Optional[datetime]
    reviewed_by: Optional[UUID]

    class Config:
        from_attributes = True
        populate_by_name = True

class ApplicationReviewRequest(BaseModel):
    rejection_reason: Optional[str] = None

class CreditAccountResponse(BaseModel):
    credit_account_id: UUID = Field(validation_alias="id")
    application_id: Optional[UUID] = None # Will be populated manually or via mapping
    cif_id: str = Field(validation_alias="customer_cif_id", default="PENDING")
    credit_product_id: UUID
    card_product_id: Optional[UUID] = None
    
    account_currency: str
    sanctioned_limit: float
    available_limit: float
    outstanding_amount: float
    
    account_status: AccountStatus
    opened_at: datetime
    
    created_by: Optional[UUID] = None
    approved_by: Optional[UUID] = None

    class Config:
        from_attributes = True
        populate_by_name = True

class ApplicationApprovedResponse(BaseModel):
    credit_account_id: UUID
    application_status: ApplicationStatus = ApplicationStatus.APPROVED
    account_details: CreditAccountResponse
    message: Optional[str] = None

class ApplicationRejectedResponse(BaseModel):
    application_status: ApplicationStatus = ApplicationStatus.REJECTED
    rejection_reason: Optional[str] = None
    message: Optional[str] = None

ApplicationReviewResponse = Union[ApplicationApprovedResponse, ApplicationRejectedResponse]

# =====================================================
# CARD ISSUANCE
# =====================================================
class CardCreate(BaseModel):
    card_type: CardType = CardType.PRIMARY

class CardResponse(BaseModel):
    id: UUID
    credit_account_id: UUID
    card_type: CardType
    
    # SECURITY: We ONLY return the masked PAN
    pan_masked: str
    expiry_date_masked: str
    cvv_masked: str
    
    card_status: CardStatus
    issued_at: datetime

    class Config:
        from_attributes = True

class CustomerCardResponse(CardResponse):
    card_holder_name: str
    credit_limit: float
    available_limit: float
    outstanding_amount: float
    card_network: str
    card_variant: str
    account_currency: str = "INR"

# Handle forward reference rebuilds if necessary (Pydantic V2 style)
# ApplicationApprovedResponse.model_rebuild()
