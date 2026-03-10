from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator
from uuid import UUID
from datetime import datetime

class ApplicationCreateRequest(BaseModel):
    credit_product_code: str
    card_product_id: UUID
    declared_income: float = Field(..., ge=1)
    income_frequency: str = "ANNUAL"
    employment_status: str
    occupation: Optional[str] = None
    employer_name: Optional[str] = None
    work_experience_years: Optional[int] = Field(None, ge=0)
    
    existing_emis_monthly: Optional[float] = Field(0.0, ge=0)
    has_existing_credit_card: bool = False
    existing_cards_count: Optional[int] = Field(0, ge=0)
    approx_credit_limit_total: Optional[float] = Field(0.0, ge=0)

    residential_status: str
    years_at_current_address: int = Field(..., ge=0)

    preferred_billing_cycle: str
    statement_delivery_mode: str

    card_delivery_address_type: str
    preferred_branch_code: str

    nominee_name: Optional[str] = None
    nominee_relationship: Optional[str] = None

    consent_terms_accepted: bool
    consent_credit_bureau_check: bool
    consent_marketing_communication: bool = False
    application_declaration_accepted: bool

    @field_validator("consent_terms_accepted", "consent_credit_bureau_check", "application_declaration_accepted")
    def validate_mandatory_consent(cls, v):
        if not v:
            raise ValueError("Mandatory consent must be accepted")
        return v

class ApplicationSummaryResponse(BaseModel):
    application_id: UUID
    status: str
    current_stage: str
    summary_message: str
    submitted_data_summary: dict
    class Config:
        from_attributes = True
    
class ApplicationResponse(BaseModel):
    id: UUID
    cif_id: UUID
    user_id: UUID
    credit_product_id: UUID
    card_product_id: UUID
    application_status: str
    current_stage: str
    submitted_at: datetime
    class Config:
        from_attributes = True

class BureauReportResponse(BaseModel):
    id: UUID
    application_id: UUID
    bureau_score: int
    report_reference_id: str
    bureau_snapshot: Optional[Dict[str, Any]] = None
    generated_at: datetime
    class Config:
        from_attributes = True

class RiskAssessmentResponse(BaseModel):
    id: UUID
    application_id: UUID
    risk_band: str
    confidence_score: Optional[float] = None
    assessment_explanation: Optional[str] = None
    assessed_at: datetime
    class Config:
        from_attributes = True

class FraudFlagResponse(BaseModel):
    id: UUID
    application_id: UUID
    flag_code: str
    flag_description: Optional[str] = None
    severity: str
    flagged_at: datetime
    class Config:
        from_attributes = True

class CreditDecisionCreate(BaseModel):
    decision: str # APPROVED, REJECTED
    override_flag: bool = False
    notes: Optional[str] = None

class CreditDecisionResponse(BaseModel):
    id: UUID
    application_id: UUID
    admin_id: UUID
    decision: str
    override_flag: bool
    notes: Optional[str]
    decided_at: datetime
    class Config:
        from_attributes = True
