from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List
from sqlalchemy import func

from app.api.deps import get_db, get_current_admin_user
from app.models.auth import User
from app.models.customer import CustomerProfile
from app.admin.models.card_issuance import CreditAccount, Card
from app.admin.schemas.user_mgmt import AdminUserSummaryResponse, AdminUserDetailsResponse, CreditAccountDetail, CardDetail

router = APIRouter(prefix="/customers", tags=["Admin: User Management"])

@router.get("/", response_model=List[AdminUserSummaryResponse])
def list_cif_completed_users(
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """Retrieves all users who have completed CIF onboarding, returning their cif_id, credit_account_id, card_id, and account_status."""
    # Join User -> Profile -> Account -> Card
    # Using outer joins to capture users who finished CIF but might not have cards yet
    results = db.query(
        CustomerProfile.cif_number.label("cif_id"),
        CreditAccount.id.label("credit_account_id"),
        Card.id.label("card_id"),
        CreditAccount.account_status.label("account_status")
    ).select_from(User).join(
        CustomerProfile, User.id == CustomerProfile.user_id
    ).outerjoin(
        CreditAccount, CustomerProfile.id == CreditAccount.cif_id
    ).outerjoin(
        Card, CreditAccount.id == Card.credit_account_id
    ).filter(
        User.is_cif_completed == True
    ).all()

    return results

@router.get("/{user_id}", response_model=AdminUserDetailsResponse)
def get_user_admin_detail(
    user_id: UUID,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """Retrieves comprehensive admin view of a user by UUID, including profile details, total credit accounts, total cards, and nested account-to-card mappings."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    profile = db.query(CustomerProfile).filter(CustomerProfile.user_id == user.id).first()
    
    accounts = db.query(CreditAccount).filter(CreditAccount.cif_id == profile.id).all() if profile else []
    
    account_details = []
    total_cards = 0
    
    for acc in accounts:
        cards = db.query(Card).filter(Card.credit_account_id == acc.id).all()
        card_list = [
            CardDetail(
                card_id=c.id,
                card_readable_id=c.readable_id,
                card_status=c.card_status,
                pan_masked=c.pan_masked
            ) for c in cards
        ]
        total_cards += len(card_list)
        
        account_details.append(
            CreditAccountDetail(
                credit_account_id=acc.id,
                readable_id=acc.readable_id,
                account_status=acc.account_status,
                cards=card_list
            )
        )

    return AdminUserDetailsResponse(
        user_id=user.id,
        email=user.email,
        phone_number=user.phone_number,
        is_cif_completed=user.is_cif_completed,
        is_kyc_completed=getattr(user, "is_kyc_completed", False),
        first_name=profile.first_name if profile else None,
        last_name=profile.last_name if profile else None,
        cif_number=profile.cif_number if profile else None,
        total_credit_accounts=len(accounts),
        total_cards=total_cards,
        credit_accounts=account_details
    )
