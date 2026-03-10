from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List

from app.api.deps import get_db, get_current_admin_user
from app.models.auth import User
from app.admin.schemas.card_issuance import (
    CreditCardApplicationResponse,
    CreditCardApplicationSummary, CreditAccountResponse, CardResponse, CardCreate,
    ApplicationReviewResponse, ApplicationReviewRequest
)
from app.models.enums import ApplicationStatus
from app.admin.models.card_issuance import CreditCardApplication
from app.admin.services.issuance_svc import CardIssuanceService

router = APIRouter(prefix="/admin/credit-applications", tags=["Admin: Credit Applications"])

@router.get("/", response_model=List[CreditCardApplicationSummary])
def get_all_applications(
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """
    Fetch all credit applications setup for Admin Listing.
    """
    return db.query(CreditCardApplication).all()

@router.get("/{application_id}", response_model=CreditCardApplicationResponse)
def get_application_details(
    application_id: UUID,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """
    Fetch full details of an application.
    """
    app = db.query(CreditCardApplication).filter(CreditCardApplication.id == application_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    
    # Auto-generate assessments if missing
    CardIssuanceService.run_engines(db, app)
    
    return app

@router.post("/{application_id}", response_model=ApplicationReviewResponse)
def review_application(
    application_id: UUID,
    command: str,
    data: ApplicationReviewRequest = None,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """
    Review a Credit Card Application.
    """
    if command not in ["approve", "reject"]:
        raise HTTPException(status_code=400, detail="Invalid command")
    
    status_to_apply = ApplicationStatus.APPROVED if command == "approve" else ApplicationStatus.REJECTED
    rejection_reason = data.rejection_reason if data else None
    
    return CardIssuanceService.review_application(db, application_id, admin.id, status_to_apply, rejection_reason)

@router.post("/accounts/{credit_account_id}/cards", response_model=CardResponse)
def issue_card_for_account(
    credit_account_id: UUID,
    data: CardCreate,
    command: str,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """
    Manually issue a printed card against an existing credit account.
    Returns only masked PAN for security.
    """
    if command != "issue_card":
        raise HTTPException(status_code=400, detail="Invalid command")
    
    return CardIssuanceService.issue_card(db, credit_account_id, data.card_type)
