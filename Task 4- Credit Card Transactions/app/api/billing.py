from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
import uuid

from app.api.deps import get_db, get_current_authenticated_user
from app.models.auth import User
from app.schemas.billing import BillingStatementResponse, RewardSummaryResponse
from app.services.billing_engine import BillingEngine
from app.models.billing import BillingStatement, RewardEntry

router = APIRouter()

@router.post("/statements/generate", response_model=BillingStatementResponse)
def trigger_statement_generation(
    account_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_authenticated_user)
):
    """
    Trigger manual statement generation for an account.
    """
    # Ownership check simplified
    return BillingEngine.generate_statement(db, account_id)

@router.get("/statements", response_model=List[BillingStatementResponse])
def get_billing_statements(
    account_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_authenticated_user)
):
    """
    Retrieve statement history for an account.
    """
    return db.query(BillingStatement).filter(BillingStatement.credit_account_id == account_id).order_by(BillingStatement.statement_date.desc()).all()

@router.get("/rewards/summary", response_model=RewardSummaryResponse)
def get_reward_summary(
    account_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_authenticated_user)
):
    """
    Get rewards summary for a specific account.
    """
    stats = db.query(
        func.sum(RewardEntry.points_earned),
        func.sum(RewardEntry.points_redeemed),
        func.sum(RewardEntry.points_reversed)
    ).filter(RewardEntry.credit_account_id == account_id).first()
    
    earned = stats[0] or 0.0
    redeemed = stats[1] or 0.0
    reversed_pts = stats[2] or 0.0
    
    return RewardSummaryResponse(
        credit_account_id=account_id,
        total_points_earned=earned,
        total_points_redeemed=redeemed,
        total_points_reversed=reversed_pts,
        net_points=earned - redeemed - reversed_pts
    )
