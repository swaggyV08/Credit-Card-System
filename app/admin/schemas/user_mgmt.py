from pydantic import BaseModel, ConfigDict
from uuid import UUID
from typing import List, Optional
from datetime import datetime
from app.models.enums import AccountStatus, CardStatus

class AdminUserSummaryResponse(BaseModel):
    user_id: str
    credit_account_id: Optional[UUID]
    card_id: Optional[UUID]
    account_status: Optional[AccountStatus]

    model_config = ConfigDict(from_attributes=True)

class CardDetail(BaseModel):
    card_id: UUID
    card_readable_id: str
    card_status: CardStatus
    pan_masked: str

class CreditAccountDetail(BaseModel):
    credit_account_id: UUID
    readable_id: str
    account_status: AccountStatus
    cards: List[CardDetail]

class AdminUserDetailsResponse(BaseModel):
    user_id: str
    email: str
    phone_number: str
    full_name: Optional[str]
    is_kyc_completed: bool
    is_cif_completed: bool
    
    total_credit_accounts: int
    total_cards: int
    credit_accounts: List[CreditAccountDetail]

    model_config = ConfigDict(from_attributes=True)
