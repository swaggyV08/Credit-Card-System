from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List
import uuid

from app.api.deps import get_current_admin_user, get_db
from app.models.admin import Admin
from app.schemas.transaction import TransactionResponse
from app.models.card_management import CCMCardTransaction
from app.models.enums import CCMTransactionStatus

router = APIRouter()

@router.get("/monitoring", response_model=List[TransactionResponse])
def monitor_all_transactions(
    status: CCMTransactionStatus = Query(None),
    min_amount: float = Query(None),
    limit: int = Query(50),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    admin: Admin = Depends(get_current_admin_user)
):
    """
    Admin-only: Monitor all transactions across the system.
    Used for fraud detection and high-value transaction monitoring.
    """
    query = db.query(CCMCardTransaction)
    
    if status:
        query = query.filter(CCMCardTransaction.status == status)
    if min_amount:
        query = query.filter(CCMCardTransaction.amount >= min_amount)
        
    return query.order_by(CCMCardTransaction.created_at.desc()).limit(limit).offset(offset).all()

@router.get("/failed", response_model=List[TransactionResponse])
def view_failed_transactions(
    db: Session = Depends(get_db),
    admin: Admin = Depends(get_current_admin_user)
):
    """
    Admin-only: View failed transactions for troubleshooting.
    """
    return db.query(CCMCardTransaction).filter(CCMCardTransaction.status == CCMTransactionStatus.FAILED).order_by(CCMCardTransaction.created_at.desc()).all()
