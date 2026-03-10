from typing import List, Optional, Any
from pydantic import BaseModel, Field, condecimal
from uuid import UUID
from datetime import datetime
from app.models.enums import (
    ProductCategory, ProductStatus, InterestType, InterestCalculationMethod,
    InterestBasis, Country, AMLRiskCategory, TaxApplicability
)

# Nested Create Schemas
class CreditProductLimitsCreate(BaseModel):
    min_credit_limit: float = Field(..., gt=0)
    max_credit_limit: float = Field(..., gt=0)
    max_total_exposure_per_cif: float = Field(..., gt=0)
    revolving_credit_allowed: bool = True
    overlimit_allowed: bool = False
    overlimit_percentage: float = 0.0

class CreditProductInterestFrameworkCreate(BaseModel):
    interest_type: InterestType = InterestType.FIXED
    base_interest_rate: float = Field(..., ge=0)
    interest_calculation_method: InterestCalculationMethod = InterestCalculationMethod.AVERAGE_DAILY_BALANCE
    interest_basis: InterestBasis = InterestBasis.ACTUAL_360
    penal_interest_rate: float = Field(..., ge=0)
    interest_free_allowed: bool = True
    max_interest_free_days: int = 50

class CreditProductFeesCreate(BaseModel):
    joining_fee: float = 0.0
    annual_fee: float = 0.0
    renewal_fee: float = 0.0
    late_payment_fee: float = 0.0
    overlimit_fee: float = 0.0
    cash_advance_fee: float = 0.0



class CreditProductEligibilityRulesCreate(BaseModel):
    min_age: int = 18
    max_age: int = 70
    min_income_required: float = Field(..., ge=0)
    employment_types_allowed: List[str]
    min_credit_score: int = 750
    secured_flag: bool = False

class CreditProductComplianceMetadataCreate(BaseModel):
    regulatory_product_code: str
    kyc_level_required: str = "FULL_KYC"
    aml_risk_category: AMLRiskCategory = AMLRiskCategory.MEDIUM
    jurisdiction: Country = Country.INDIA
    tax_applicability: TaxApplicability = TaxApplicability.GST_APPLICABLE
    statement_disclosure_version: str
    regulatory_reporting_category: str

class CreditProductAccountingMappingCreate(BaseModel):
    principal_gl_code: str
    interest_income_gl_code: str
    fee_income_gl_code: str
    penalty_gl_code: str
    writeoff_gl_code: str

# Aggregate Create Schema
class CreditProductCreate(BaseModel):
    product_name: str
    product_category: ProductCategory = ProductCategory.CARD
    product_sub_category: Optional[str] = None
    
    limits: CreditProductLimitsCreate
    interest_framework: CreditProductInterestFrameworkCreate
    fees: CreditProductFeesCreate
    eligibility_rules: CreditProductEligibilityRulesCreate
    compliance_metadata: CreditProductComplianceMetadataCreate
    accounting_mapping: CreditProductAccountingMappingCreate
    
    auto_renewal_allowed: bool = True
    cooling_period_days: int = 90

# Update Schema
class CreditProductUpdate(BaseModel):
    product_name: Optional[str] = None
    product_sub_category: Optional[str] = None
    status: Optional[ProductStatus] = None # Mainly for suspension/closure

# Response Schemas
class CreditProductLimitsResponse(CreditProductLimitsCreate):
    class Config:
        from_attributes = True

class CreditProductInterestFrameworkResponse(CreditProductInterestFrameworkCreate):
    class Config:
        from_attributes = True

class CreditProductFeesResponse(CreditProductFeesCreate):
    class Config:
        from_attributes = True



class CreditProductEligibilityRulesResponse(CreditProductEligibilityRulesCreate):
    class Config:
        from_attributes = True

class CreditProductComplianceMetadataResponse(CreditProductComplianceMetadataCreate):
    class Config:
        from_attributes = True

class CreditProductAccountingMappingResponse(CreditProductAccountingMappingCreate):
    class Config:
        from_attributes = True

class CreditProductGovernanceResponse(BaseModel):
    card_product_version: Optional[int] = None
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None
    created_at: datetime
    created_by: UUID
    approved_by: Optional[UUID] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[UUID] = None
    class Config:
        from_attributes = True

class CreditProductResponse(BaseModel):
    product_id: UUID = Field(validation_alias="id")
    product_code: str
    product_name: str
    product_category: ProductCategory
    product_sub_category: Optional[str]
    product_version: int
    status: ProductStatus
    
    limits: Optional[CreditProductLimitsResponse]
    interest_framework: Optional[CreditProductInterestFrameworkResponse]
    fees: Optional[CreditProductFeesResponse]
    eligibility_rules: Optional[CreditProductEligibilityRulesResponse]
    compliance_metadata: Optional[CreditProductComplianceMetadataResponse]
    accounting_mapping: Optional[CreditProductAccountingMappingResponse]
    governance: Optional[CreditProductGovernanceResponse]

    class Config:
        from_attributes = True

class CreditProductCreateResponse(BaseModel):
    product_id: UUID = Field(validation_alias="id")
    product_code: str
    product_name: str

class DateInput(BaseModel):
    day: int
    month: int
    year: int

class CreditProductApprovalRequest(BaseModel):
    effective_to: Optional[DateInput] = None
    reject_reason: Optional[str] = None

class CreditProductStatusUpdateResponse(BaseModel):
    message: str
    product_id: UUID
    product_code: str
    product_name: str
    reject_reason: Optional[str] = None

    class Config:
        from_attributes = True

class CreditProductSummaryResponse(BaseModel):
    product_id: UUID = Field(validation_alias="id")
    product_code: str
    product_name: str
    status: ProductStatus

    class Config:
        from_attributes = True
