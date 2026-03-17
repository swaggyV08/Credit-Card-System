from typing import List, Optional, Any
from pydantic import BaseModel, Field, condecimal, ConfigDict, field_validator
from uuid import UUID
from datetime import datetime
from decimal import Decimal
from app.models.enums import (
    ProductCategory, ProductStatus, InterestType, InterestCalculationMethod,
    InterestBasis, Country, AMLRiskCategory, TaxApplicability
)

class CreditProductLimitsCreate(BaseModel):
    min_credit_limit: condecimal(max_digits=13, decimal_places=3, gt=0) = Field(..., description="Minimum credit limit", json_schema_extra={"example": "0000000000.000"})
    max_credit_limit: condecimal(max_digits=13, decimal_places=3, gt=0) = Field(..., description="Maximum credit limit", json_schema_extra={"example": "0000000000.000"})
    max_total_exposure_per_cif: condecimal(max_digits=13, decimal_places=3, gt=0) = Field(..., description="Max exposure", json_schema_extra={"example": "0000000000.000"})
    revolving_credit_allowed: bool = Field(True, description="Revolving allowed")
    overlimit_allowed: bool = Field(False, description="Overlimit allowed")
    overlimit_percentage: condecimal(max_digits=13, decimal_places=3) = Field(Decimal("0.0"), description="Overlimit %", json_schema_extra={"example": "0000000000.000"})

class CreditProductInterestFrameworkCreate(BaseModel):
    interest_type: InterestType = Field(InterestType.FIXED, description="Interest type")
    base_interest_rate: condecimal(max_digits=13, decimal_places=3, ge=0) = Field(..., description="Base rate", json_schema_extra={"example": "0000000000.000"})
    interest_calculation_method: InterestCalculationMethod = Field(InterestCalculationMethod.AVERAGE_DAILY_BALANCE, description="Method")
    interest_basis: InterestBasis = Field(InterestBasis.ACTUAL_360, description="Basis")
    penal_interest_rate: condecimal(max_digits=13, decimal_places=3, ge=0) = Field(..., description="Penal rate", json_schema_extra={"example": "0000000000.000"})
    interest_free_allowed: bool = Field(True, description="Interest free allowed")
    max_interest_free_days: int = Field(30, le=30, description="Max free days")

class CreditProductFeesCreate(BaseModel):
    joining_fee: condecimal(max_digits=13, decimal_places=3) = Field(Decimal("0.0"), description="Joining fee", json_schema_extra={"example": "0000000000.000"})
    annual_fee: condecimal(max_digits=13, decimal_places=3) = Field(Decimal("0.0"), description="Annual fee", json_schema_extra={"example": "0000000000.000"})
    renewal_fee: condecimal(max_digits=13, decimal_places=3) = Field(Decimal("0.0"), description="Renewal fee", json_schema_extra={"example": "0000000000.000"})
    late_payment_fee: condecimal(max_digits=13, decimal_places=3) = Field(Decimal("0.0"), description="Late fee", json_schema_extra={"example": "0000000000.000"})
    overlimit_fee: condecimal(max_digits=13, decimal_places=3) = Field(Decimal("0.0"), description="Overlimit fee", json_schema_extra={"example": "0000000000.000"})
    cash_advance_fee: condecimal(max_digits=13, decimal_places=3) = Field(Decimal("0.0"), description="Cash fee", json_schema_extra={"example": "0000000000.000"})

class CreditProductEligibilityRulesCreate(BaseModel):
    min_age: int = Field(18, description="Min age")
    max_age: int = Field(70, description="Max age")
    min_income_required: condecimal(max_digits=13, decimal_places=3, ge=0) = Field(..., description="Min income", json_schema_extra={"example": "0000000000.000"})
    employment_types_allowed: List[str] = Field(..., description="Employment allowed")
    min_credit_score: int = Field(750, description="Min score")
    secured_flag: bool = False

class CreditProductComplianceMetadataCreate(BaseModel):
    regulatory_product_code: str = Field(..., description="Reg code")
    kyc_level_required: str = Field("FULL_KYC", description="KYC level")
    aml_risk_category: AMLRiskCategory = Field(AMLRiskCategory.MEDIUM, description="AML Risk")
    jurisdiction: Country = Field(Country.INDIA, description="Jurisdiction")
    tax_applicability: TaxApplicability = Field(TaxApplicability.GST_APPLICABLE, description="Tax rule")
    statement_disclosure_version: str = Field(..., description="Disclosure version")
    regulatory_reporting_category: str = Field(..., description="Reporting category")

    @field_validator("regulatory_product_code", "regulatory_reporting_category", mode="before")
    @classmethod
    def lowercase_codes(cls, v):
        if isinstance(v, str):
            return v.lower().strip()
        return v

class CreditProductAccountingMappingCreate(BaseModel):
    principal_gl_code: str = Field(..., description="Principal GL")
    interest_income_gl_code: str = Field(..., description="Interest GL")
    fee_income_gl_code: str = Field(..., description="Fee GL")
    penalty_gl_code: str = Field(..., description="Penalty GL")
    writeoff_gl_code: str = Field(..., description="Writeoff GL")

    @field_validator("*", mode="before")
    @classmethod
    def normalize_gl_codes(cls, v):
        if isinstance(v, str):
            return v.lower().strip()
        return v

class CreditProductCreate(BaseModel):
    product_name: str
    product_category: ProductCategory = ProductCategory.CARD
    limits: CreditProductLimitsCreate
    interest_framework: CreditProductInterestFrameworkCreate
    fees: CreditProductFeesCreate
    eligibility_rules: CreditProductEligibilityRulesCreate
    compliance_metadata: CreditProductComplianceMetadataCreate
    accounting_mapping: CreditProductAccountingMappingCreate
    auto_renewal_allowed: bool = True
    cooling_period_days: int = 90

class CreditProductUpdate(BaseModel):
    product_name: Optional[str] = None
    status: Optional[ProductStatus] = None

class CreditProductLimitsResponse(CreditProductLimitsCreate):
    model_config = ConfigDict(from_attributes=True)

class CreditProductInterestFrameworkResponse(CreditProductInterestFrameworkCreate):
    model_config = ConfigDict(from_attributes=True)

class CreditProductFeesResponse(CreditProductFeesCreate):
    model_config = ConfigDict(from_attributes=True)

class CreditProductEligibilityRulesResponse(CreditProductEligibilityRulesCreate):
    model_config = ConfigDict(from_attributes=True)

class CreditProductComplianceMetadataResponse(CreditProductComplianceMetadataCreate):
    model_config = ConfigDict(from_attributes=True)

class CreditProductAccountingMappingResponse(CreditProductAccountingMappingCreate):
    model_config = ConfigDict(from_attributes=True)

class CreditProductGovernanceResponse(BaseModel):
    card_product_version: Optional[int] = None
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None
    created_at: datetime
    created_by: UUID
    approved_by: Optional[UUID] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[UUID] = None
    model_config = ConfigDict(from_attributes=True)

class CreditProductResponse(BaseModel):
    product_id: UUID = Field(validation_alias="id")
    product_code: str
    product_name: str
    product_category: ProductCategory
    product_version: int
    status: ProductStatus
    limits: Optional[CreditProductLimitsResponse]
    interest_framework: Optional[CreditProductInterestFrameworkResponse]
    fees: Optional[CreditProductFeesResponse]
    eligibility_rules: Optional[CreditProductEligibilityRulesResponse]
    compliance_metadata: Optional[CreditProductComplianceMetadataResponse]
    accounting_mapping: Optional[CreditProductAccountingMappingResponse]
    governance: Optional[CreditProductGovernanceResponse]
    model_config = ConfigDict(from_attributes=True)

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
    model_config = ConfigDict(from_attributes=True)

class CreditProductSummaryResponse(BaseModel):
    product_id: UUID = Field(validation_alias="id")
    product_code: str
    product_name: str
    status: ProductStatus
    model_config = ConfigDict(from_attributes=True)
