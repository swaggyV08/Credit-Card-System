from typing import Optional
from enum import Enum
from pydantic import BaseModel, ConfigDict
from .credit_account_admin import (
    CreditLimitUpdateRequest, AccountStatusUpdateRequest,
    AccountFreezeRequest, BillingCycleUpdateRequest,
    RiskFlagUpdateRequest, InterestUpdateRequest,
    OverlimitConfigRequest
)

class AdminAccountCommand(str, Enum):
    LIMIT = "limit"
    STATUS = "status"
    FREEZE = "freeze"
    BILLING_CYCLE = "billing_cycle"
    RISK = "risk"
    INTEREST = "interest"
    OVERLIMIT = "overlimit"

class UnifiedAccountUpdateRequest(BaseModel):
    limits: Optional[CreditLimitUpdateRequest] = None
    status: Optional[AccountStatusUpdateRequest] = None
    freeze: Optional[AccountFreezeRequest] = None
    billing_cycle: Optional[BillingCycleUpdateRequest] = None
    risk: Optional[RiskFlagUpdateRequest] = None
    interest: Optional[InterestUpdateRequest] = None
    overlimit: Optional[OverlimitConfigRequest] = None

    model_config = ConfigDict(populate_by_name=True)
