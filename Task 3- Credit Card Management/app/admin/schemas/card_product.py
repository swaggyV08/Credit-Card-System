from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
from uuid import UUID
from datetime import datetime
from app.models.enums import (
    CardNetwork, CardFormFactor, CardVariant, BillingCycleType,
    StatementGenerationMode, RewardAccrualType, RewardExpiryPolicy,
    FraudMonitoringProfile, VelocityCheckProfile, ProductStatus
)

class EffectiveToSchema(BaseModel):
    day: int = Field(..., ge=1, le=31)
    month: int = Field(..., ge=1, le=12)
    year: int = Field(..., ge=2024)

    @model_validator(mode='after')
    def validate_future_date(self) -> 'EffectiveToSchema':
        from datetime import date
        try:
            input_date = date(self.year, self.month, self.day)
            if input_date < date.today():
                raise ValueError("Effective date must be today or in the future.")
        except ValueError as e:
            if "Effective date" in str(e):
                raise
            raise ValueError("Invalid date provided.")
        return self

class CardProductApprovalRequest(BaseModel):
    effective_to: Optional[EffectiveToSchema] = None

# Nested Create Schemas
class CardBillingConfigurationCreate(BaseModel):
    billing_cycle_type: BillingCycleType = BillingCycleType.MONTHLY
    billing_cycle_day: int = Field(..., ge=1, le=31)
    payment_due_days: int = Field(..., ge=1, le=31)
    minimum_due_formula: str = "5_PCT_OF_BILL"
    statement_generation_mode: StatementGenerationMode = StatementGenerationMode.ELECTRONIC
    statement_currency: str = "INR"
    grace_period_days: int = Field(..., ge=0)

class CardTransactionControlsCreate(BaseModel):
    pos_allowed: bool = True
    ecommerce_allowed: bool = True
    atm_withdrawal_allowed: bool = False
    contactless_enabled: bool = True
    international_txn_allowed: bool = False
    international_txn_limit_cap: Optional[float] = None
    international_cash_allowed: bool = False
    tokenization_supported: bool = True
    recurring_txn_allowed: bool = True

class CardFxConfigurationCreate(BaseModel):
    supported_currencies: Optional[List[str]] = None
    fx_rate_source: str = "VISA"
    fx_conversion_method: str = "MARKET_RATE"
    foreign_markup_fee_pct: float = 3.5
    cross_border_fee_applicable: bool = True
    cross_border_fee_rate: float = 1.0

class CardUsageLimitsCreate(BaseModel):
    cash_advance_limit_pct: float = Field(..., ge=0, le=100)
    domestic_txn_daily_cap: float = Field(..., ge=0)
    contactless_txn_cap: float = Field(..., ge=0)
    max_txn_per_day: int = Field(..., ge=1)

class CardRewardsConfigurationCreate(BaseModel):
    reward_program_code: str
    reward_accrual_type: RewardAccrualType = RewardAccrualType.POINTS
    reward_earn_rate: float = Field(..., ge=0)
    reward_expiry_policy: RewardExpiryPolicy = RewardExpiryPolicy.TWO_YEARS
    reward_redemption_modes: List[str]
    merchant_category_bonus: Optional[Dict[str, float]] = None

    @field_validator("reward_program_code", mode="before")
    @classmethod
    def lowercase_reward_code(cls, v):
        if isinstance(v, str):
            return v.lower().strip()
        return v

class CardAuthorizationRulesCreate(BaseModel):
    partial_auth_allowed: bool = False
    offline_txn_allowed: bool = False
    authorization_ttl_seconds: int = 604800
    retry_authorization_allowed: bool = True
    network_stand_in_allowed: bool = True

class CardLifecycleRulesCreate(BaseModel):
    card_validity_years: int = Field(..., ge=1, le=10)
    auto_renew_card: bool = True
    replacement_reason_codes: List[str]
    reissue_fee_applicable: bool = True
    temporary_block_supported: bool = True

class CardFraudRiskProfileCreate(BaseModel):
    fraud_monitoring_profile: FraudMonitoringProfile = FraudMonitoringProfile.STANDARD
    velocity_check_profile: VelocityCheckProfile = VelocityCheckProfile.STANDARD
    geo_blocking_supported: bool = True
    fallback_auth_allowed: bool = False

# Aggregate Create Schema
class CardProductCreate(BaseModel):
    credit_product_code: str
    card_network: CardNetwork
    card_bin_range: str
    card_branding_code: str
    card_form_factor: CardFormFactor = CardFormFactor.PHYSICAL
    card_variant: CardVariant = CardVariant.CLASSIC
    default_card_currency: str = "INR"
    
    billing_config: CardBillingConfigurationCreate
    transaction_controls: CardTransactionControlsCreate
    fx_configuration: CardFxConfigurationCreate
    usage_limits: CardUsageLimitsCreate
    rewards_config: CardRewardsConfigurationCreate
    authorization_rules: CardAuthorizationRulesCreate
    lifecycle_rules: CardLifecycleRulesCreate
    fraud_profile: CardFraudRiskProfileCreate
    
    @field_validator("credit_product_code", "card_bin_range", "card_branding_code", mode="before")
    @classmethod
    def lowercase_codes(cls, v):
        if isinstance(v, str):
            return v.lower().strip()
        return v
    
# Update Schema
class CardProductUpdate(BaseModel):
    status: Optional[ProductStatus] = None # Mainly for suspension/closure

# Response Schemas

class CardBillingConfigurationResponse(CardBillingConfigurationCreate):
    id: UUID
    model_config = ConfigDict(from_attributes=True)

class CardTransactionControlsResponse(CardTransactionControlsCreate):
    id: UUID
    model_config = ConfigDict(from_attributes=True)

class CardFxConfigurationResponse(CardFxConfigurationCreate):
    id: UUID
    model_config = ConfigDict(from_attributes=True)

class CardUsageLimitsResponse(CardUsageLimitsCreate):
    id: UUID
    model_config = ConfigDict(from_attributes=True)

class CardRewardsConfigurationResponse(CardRewardsConfigurationCreate):
    id: UUID
    model_config = ConfigDict(from_attributes=True)

class CardAuthorizationRulesResponse(CardAuthorizationRulesCreate):
    id: UUID
    model_config = ConfigDict(from_attributes=True)

class CardLifecycleRulesResponse(CardLifecycleRulesCreate):
    id: UUID
    model_config = ConfigDict(from_attributes=True)

class CardFraudRiskProfileResponse(CardFraudRiskProfileCreate):
    id: UUID
    model_config = ConfigDict(from_attributes=True)

class CardProductGovernanceResponse(BaseModel):
    id: UUID
    card_product_version: int
    status: ProductStatus
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None
    created_at: datetime
    created_by: UUID
    approved_by: Optional[UUID] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[UUID] = None
    model_config = ConfigDict(from_attributes=True)

class CardProductResponse(BaseModel):
    card_product_id: UUID = Field(validation_alias="id")
    credit_product_id: UUID
    card_network: CardNetwork
    card_bin_range: str
    card_branding_code: str
    card_form_factor: CardFormFactor
    card_variant: CardVariant
    default_card_currency: str
    
    billing_config: Optional[CardBillingConfigurationResponse]
    transaction_controls: Optional[CardTransactionControlsResponse]
    fx_configuration: Optional[CardFxConfigurationResponse]
    usage_limits: Optional[CardUsageLimitsResponse]
    rewards_config: Optional[CardRewardsConfigurationResponse]
    authorization_rules: Optional[CardAuthorizationRulesResponse]
    lifecycle_rules: Optional[CardLifecycleRulesResponse]
    fraud_profile: Optional[CardFraudRiskProfileResponse]
    governance: Optional[CardProductGovernanceResponse]

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

class CardProductCreateResponse(BaseModel):
    card_product_id: UUID = Field(validation_alias="id")
    credit_product_id: UUID
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None
    created_at: datetime
    created_by: UUID

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

class CardProductApprovalResponse(BaseModel):
    card_product_id: UUID = Field(validation_alias="id")
    credit_product_id: UUID
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None
    created_at: datetime
    created_by: UUID
    approved_by: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

class CardProductSummaryResponse(BaseModel):
    card_product_id: UUID = Field(validation_alias="id")
    credit_product_id: UUID
    card_network: CardNetwork
    card_variant: CardVariant
    status: ProductStatus

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
