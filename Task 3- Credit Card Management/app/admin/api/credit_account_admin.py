from fastapi import APIRouter, Depends, Query, Path
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional, List
from datetime import date, datetime, timedelta

from app.api import deps
from app.admin.services.credit_account_admin_svc import CreditAccountAdminService
from app.admin.schemas.credit_account_admin import (
    PaginatedAccountsResponse, CreditAccountDetail,
    CreditLimitUpdateRequest, CreditLimitUpdateResponse,
    AccountStatusUpdateRequest, AccountStatusUpdateResponse,
    AccountFreezeRequest, AccountFreezeResponse,
    BillingCycleUpdateRequest, BillingCycleUpdateResponse,
    RiskFlagUpdateRequest, RiskFlagUpdateResponse,
    InterestUpdateRequest, InterestUpdateResponse,
    OverlimitConfigRequest, OverlimitConfigResponse
)
from app.models.enums import CCMAccountStatus

router = APIRouter(prefix="/credit-accounts", tags=["Admin: Credit Accounts"])

@router.get("/", response_model=PaginatedAccountsResponse)
def list_accounts(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[CCMAccountStatus] = None,
    product_code: Optional[str] = None,
    db: Session = Depends(deps.get_db),
    admin=Depends(deps.get_current_admin_user)
):
    """Retrieves a paginated list of credit accounts with optional filters by status and product_code. Status values: PENDING, ACTIVE, SUSPENDED, FROZEN, DELINQUENT, CLOSED, CHARGED_OFF."""
    accounts, total = CreditAccountAdminService.list_accounts(
        db, page=page, limit=limit, status=status, product_code=product_code
    )
    return {
        "page": page,
        "limit": limit,
        "total_records": total,
        "accounts": accounts
    }

@router.get("/{credit_account_id}", response_model=CreditAccountDetail)
def get_account_details(
    credit_account_id: UUID = Path(...),
    db: Session = Depends(deps.get_db),
    admin=Depends(deps.get_current_admin_user)
):
    """Retrieves full details of a single credit account including balances, APRs, risk flag, overlimit config, and timestamps."""
    return CreditAccountAdminService.get_account(db, credit_account_id)

@router.patch("/{credit_account_id}/limit", response_model=CreditLimitUpdateResponse)
def update_credit_limit(
    req: CreditLimitUpdateRequest,
    credit_account_id: UUID = Path(...),
    db: Session = Depends(deps.get_db),
    admin=Depends(deps.get_current_admin_user)
):
    """Updates the credit limit for an account. reason_code values: INCOME_REVIEW, RISK_ADJUSTMENT, PROMOTIONAL, MANUAL_OVERRIDE."""
    account, old_limit = CreditAccountAdminService.update_limit(db, credit_account_id, req, admin.id)
    return {
        "credit_account_id": account.id,
        "old_credit_limit": old_limit,
        "new_credit_limit": account.credit_limit,
        "available_credit": account.available_credit,
        "updated_by": admin.id,
        "updated_at": datetime.now()
    }

@router.patch("/{credit_account_id}/status", response_model=AccountStatusUpdateResponse)
def update_account_status(
    req: AccountStatusUpdateRequest,
    credit_account_id: UUID = Path(...),
    db: Session = Depends(deps.get_db),
    admin=Depends(deps.get_current_admin_user)
):
    """Transitions the account lifecycle status. status values: PENDING, ACTIVE, SUSPENDED, FROZEN, DELINQUENT, CLOSED, CHARGED_OFF. reason_code values: KYC_REVIEW, FRAUD_ALERT, DELINQUENCY, CUSTOMER_REQUEST, COMPLIANCE, ADMIN_ACTION."""
    account, old_status = CreditAccountAdminService.update_status(db, credit_account_id, req)
    return {
        "credit_account_id": account.id,
        "previous_status": old_status,
        "new_status": account.status,
        "updated_at": datetime.now()
    }

@router.patch("/{credit_account_id}/freeze", response_model=AccountFreezeResponse)
def freeze_account(
    req: AccountFreezeRequest,
    credit_account_id: UUID = Path(...),
    db: Session = Depends(deps.get_db),
    admin=Depends(deps.get_current_admin_user)
):
    """Freezes or unfreezes an account based on the `freeze` boolean flag. reason_code values: KYC_REVIEW, FRAUD_ALERT, DELINQUENCY, CUSTOMER_REQUEST, COMPLIANCE, ADMIN_ACTION."""
    account, new_status = CreditAccountAdminService.freeze(db, credit_account_id, req)
    return {
        "credit_account_id": account.id,
        "freeze_status": "FROZEN" if req.freeze else "ACTIVE",
        "reason_code": req.reason_code,
        "updated_at": datetime.now()
    }

@router.patch("/{credit_account_id}/billing-cycle", response_model=BillingCycleUpdateResponse)
def update_billing_cycle(
    req: BillingCycleUpdateRequest,
    credit_account_id: UUID = Path(...),
    db: Session = Depends(deps.get_db),
    admin=Depends(deps.get_current_admin_user)
):
    """Updates the billing cycle day (1-28) and payment due days for an account, and returns the projected next statement date."""
    account = CreditAccountAdminService.update_billing_cycle(db, credit_account_id, req)
    # Simple projection for next statement date (fictional logic for response)
    next_date = datetime.now() + timedelta(days=30)
    return {
        "credit_account_id": account.id,
        "billing_cycle_day": account.billing_cycle_day,
        "payment_due_days": account.payment_due_days,
        "next_statement_date": next_date
    }

@router.patch("/{credit_account_id}/risk", response_model=RiskFlagUpdateResponse)
def update_risk_flag(
    req: RiskFlagUpdateRequest,
    credit_account_id: UUID = Path(...),
    db: Session = Depends(deps.get_db),
    admin=Depends(deps.get_current_admin_user)
):
    """Updates the risk classification flag for an account. risk_flag values: NONE, LOW_RISK, MEDIUM_RISK, HIGH_RISK, CRITICAL."""
    account = CreditAccountAdminService.update_risk_flag(db, credit_account_id, req)
    return {
        "credit_account_id": account.id,
        "risk_flag": account.risk_flag,
        "updated_at": datetime.now()
    }

@router.patch("/{credit_account_id}/interest", response_model=InterestUpdateResponse)
def update_interest(
    req: InterestUpdateRequest,
    credit_account_id: UUID = Path(...),
    db: Session = Depends(deps.get_db),
    admin=Depends(deps.get_current_admin_user)
):
    """Updates purchase APR, cash advance APR, and penalty APR for an account. All values must be >= 0."""
    account = CreditAccountAdminService.update_interest(db, credit_account_id, req)
    return {
        "credit_account_id": account.id,
        "purchase_apr": account.purchase_apr,
        "cash_apr": account.cash_apr,
        "penalty_apr": account.penalty_apr
    }

@router.patch("/{credit_account_id}/overlimit", response_model=OverlimitConfigResponse)
def update_overlimit_config(
    req: OverlimitConfigRequest,
    credit_account_id: UUID = Path(...),
    db: Session = Depends(deps.get_db),
    admin=Depends(deps.get_current_admin_user)
):
    """Enables or disables overlimit spending for an account, and configures the overlimit buffer amount and overlimit fee."""
    account = CreditAccountAdminService.update_overlimit(db, credit_account_id, req)
    return {
        "credit_account_id": account.id,
        "overlimit_enabled": account.overlimit_enabled,
        "overlimit_buffer": account.overlimit_buffer,
        "overlimit_fee": account.overlimit_fee
    }
