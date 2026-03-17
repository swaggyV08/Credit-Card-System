from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator, ConfigDict
from uuid import UUID
from datetime import datetime, date
from decimal import Decimal

def validate_currency_10_3(v: Decimal) -> Decimal:
    if v is None: return v
    if v < 0:
        raise ValueError("Value cannot be negative")
    if v >= Decimal("10000000000"):
        raise ValueError("Value must be less than 10 digits before decimal")
    str_v = str(v)
    if "." in str_v:
        decimals = len(str_v.split(".")[1])
        if decimals > 3:
            raise ValueError("only upto 4 digits after decimal")
    return v

class ApplicationCreateRequest(BaseModel):
    credit_product_code: str = Field(..., description="Unique code of the credit product (Case-insensitive)")
    application_date: date = Field(default_factory=date.today, description="Date of application submission (Defaults to today)")
    declared_income: Decimal = Field(..., ge=1, description="Total annual income declared by the applicant")
    income_frequency: str = Field("ANNUALLY", description="Frequency of income (e.g., MONTHLY, ANNUALLY)")
    employment_status: str = Field(..., description="Current employment type (e.g., SALARIED, SELF_EMPLOYED)")
    occupation: Optional[str] = Field(None, description="Detailed occupation or job profile")
    employer_name: Optional[str] = Field(None, description="Name of the current company")
    work_experience_years: Optional[int] = Field(None, ge=0, description="Total years of professional experience")
    
    existing_emis_monthly: Optional[Decimal] = Field(Decimal("0.0"), ge=0)
    has_existing_credit_card: bool = False
    existing_cards_count: Optional[int] = Field(0, ge=0)
    approx_credit_limit_total: Optional[Decimal] = Field(Decimal("0.0"), ge=0)

    @field_validator("declared_income", "existing_emis_monthly", "approx_credit_limit_total")
    @classmethod
    def validate_app_nums(cls, v):
        return validate_currency_10_3(v)

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

    @field_validator("credit_product_code", "employment_status", "occupation", "employer_name", "income_frequency")
    @classmethod
    def normalize_strings(cls, v):
        if isinstance(v, str):
            return v.lower().strip()
        return v

    @field_validator("application_date")
    @classmethod
    def validate_not_backdated(cls, v):
        if v < date.today():
            raise ValueError("Application date cannot be in the past (Back-dated applications are invalid)")
        return v

    @field_validator("consent_terms_accepted", "consent_credit_bureau_check", "application_declaration_accepted")
    @classmethod
    def validate_mandatory_consent(cls, v):
        if not v:
            raise ValueError("Mandatory consent must be accepted to proceed with the application")
        return v

class ApplicationSummaryResponse(BaseModel):
    application_id: UUID
    status: str
    current_stage: str
    summary_message: str
    submitted_data_summary: dict
    model_config = ConfigDict(from_attributes=True)
    
class ApplicationResponse(BaseModel):
    id: UUID
    cif_id: UUID
    user_id: UUID
    credit_product_id: UUID
    card_product_id: UUID
    application_status: str
    current_stage: str
    submitted_at: datetime
    model_config = ConfigDict(from_attributes=True)

class BureauReportResponse(BaseModel):
    id: UUID
    application_id: UUID
    bureau_score: int
    report_reference_id: str
    bureau_snapshot: Optional[Dict[str, Any]] = None
    generated_at: datetime
    model_config = ConfigDict(from_attributes=True)

class RiskAssessmentResponse(BaseModel):
    id: UUID
    application_id: UUID
    risk_band: str
    confidence_score: Optional[float] = None
    assessment_explanation: Optional[str] = None
    assessed_at: datetime
    model_config = ConfigDict(from_attributes=True)

class FraudFlagResponse(BaseModel):
    id: UUID
    application_id: UUID
    flag_code: str
    flag_description: Optional[str] = None
    severity: str
    flagged_at: datetime
    model_config = ConfigDict(from_attributes=True)

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
    model_config = ConfigDict(from_attributes=True)
