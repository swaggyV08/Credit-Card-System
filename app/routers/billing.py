"""
Billing Router — Week 5

Endpoints:
  POST /billing/generate         — Admin: trigger statement generation
  GET  /cards/{card_id}/statements  — List statements (handled in statements.py)
  POST /cards/{card_id}/payments    — Payment with RBI waterfall (enhanced in payments.py)
"""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.rbac import require, AuthenticatedPrincipal
from app.schemas.base import envelope_success
from app.schemas.billing import (
    BillingGenerateRequest,
    StatementSummary,
    StatementDetail,
    PaymentCreateRequest,
    PaymentResponse,
    FraudFlagSummary,
)
from app.services.billing_service import BillingService
from app.models.billing import FraudFlag

router = APIRouter(tags=["Billing"])


@router.post("/billing/generate", status_code=200)
def generate_billing_statements(
    request: BillingGenerateRequest,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("billing:generate")),
):
    """
    Admin-only: Trigger statement generation for the specified billing cycle.

    This simulates the banking heuristic of computing ADB interest,
    applying grace periods, and generating line-item statements
    for all active credit accounts.
    """
    results = BillingService.generate_statements(
        db=db,
        cycle_date=request.cycle_date,
        purchase_apr=request.purchase_apr,
        cash_advance_apr=request.cash_advance_apr,
        generated_by=principal.user_id if hasattr(principal, 'user_id') else None,
    )
    return envelope_success({
        "statements_generated": len(results),
        "cycle_date": str(request.cycle_date),
        "details": results,
    })


@router.post("/billing/late-fees", status_code=200)
def apply_late_fees(
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("billing:generate")),
):
    """
    Admin-only: Apply late fees to all overdue statements.
    """
    results = BillingService.apply_late_fees(db)
    return envelope_success({
        "late_fees_applied": len(results),
        "details": results,
    })


@router.get("/cards/{card_id}/fraud-flags")
def list_fraud_flags(
    card_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("transaction:read")),
):
    """List all fraud flags for a card."""
    query = db.query(FraudFlag).filter(FraudFlag.card_id == card_id)
    total = query.count()
    flags = query.order_by(FraudFlag.flagged_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    data = [FraudFlagSummary.model_validate(f).model_dump(mode="json") for f in flags]
    return envelope_success({
        "data": data,
        "meta": {"total": total, "page": page, "page_size": page_size},
    })
