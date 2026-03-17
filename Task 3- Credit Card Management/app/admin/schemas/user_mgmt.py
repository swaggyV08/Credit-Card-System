from pydantic import BaseModel, ConfigDict
from uuid import UUID
from typing import List, Optional
from datetime import datetime
from app.models.enums import AccountStatus, CardStatus

class AdminUserSummaryResponse(BaseModel):
    cif_id: str
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
    user_id: UUID
    email: str
    phone_number: str
    is_cif_completed: bool
    is_kyc_completed: bool
    first_name: Optional[str]
    last_name: Optional[str]
    cif_number: Optional[str]
    
    total_credit_accounts: int
    total_cards: int
    credit_accounts: List[CreditAccountDetail]

    model_config = ConfigDict(from_attributes=True)
