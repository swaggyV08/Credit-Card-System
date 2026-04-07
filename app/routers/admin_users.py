from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List, Optional

from app.api.deps import get_db
from app.core.rbac import require, AuthenticatedPrincipal
from app.schemas.base import envelope_success
from app.core.app_error import AppError
from app.models.auth import User
from app.models.customer import CustomerProfile
from app.admin.models.card_issuance import CreditAccount, Card
from app.admin.schemas.user_mgmt import AdminUserSummaryResponse, AdminUserDetailsResponse, CreditAccountDetail, CardDetail

router = APIRouter(prefix="/customers", tags=["Admin: User Management"])

@router.get("/")
def list_cif_completed_users(
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("user:list"))
):
    """Retrieves all users who have completed CIF onboarding."""
    results = db.query(
        User.id.label("user_id"),
        CreditAccount.id.label("credit_account_id"),
        Card.id.label("card_id"),
        CreditAccount.account_status.label("account_status")
    ).select_from(User).join(
        CustomerProfile, User.id == CustomerProfile.user_id
    ).outerjoin(
        CreditAccount, User.id == CreditAccount.user_id
    ).outerjoin(
        Card, CreditAccount.id == Card.credit_account_id
    ).filter(
        User.is_cif_completed == True
    ).all()

    # Convert NamedTuple-like results to dicts
    data = []
    for r in results:
        data.append({
            "user_id": str(r.user_id),
            "credit_account_id": str(r.credit_account_id) if r.credit_account_id else None,
            "card_id": str(r.card_id) if r.card_id else None,
            "account_status": r.account_status
        })
    return envelope_success(data)

@router.get("/{user_id}")
def get_user_admin_detail(
    user_id: str,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("user:detail"))
):
    """Retrieves comprehensive admin view of a user."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise AppError(code="NOT_FOUND", message="User not found", http_status=404)

    profile = db.query(CustomerProfile).filter(CustomerProfile.user_id == user.id).first()
    accounts = db.query(CreditAccount).filter(CreditAccount.user_id == user.id).all() if profile else []
    
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

    response_data = AdminUserDetailsResponse(
        user_id=user.id,
        email=user.email,
        phone_number=user.phone_number,
        is_cif_completed=user.is_cif_completed,
        is_kyc_completed=getattr(user, "is_kyc_completed", False),
        full_name=user.full_name or (f"{profile.first_name} {profile.last_name}".strip() if profile else None),
        total_credit_accounts=len(accounts),
        total_cards=total_cards,
        credit_accounts=account_details
    )
    
    return envelope_success(response_data.model_dump(mode='json') if hasattr(response_data, 'model_dump') else response_data)
