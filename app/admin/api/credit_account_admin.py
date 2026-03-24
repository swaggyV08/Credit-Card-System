from fastapi import APIRouter, Depends, Query, Path
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional, List
from datetime import date, datetime, timedelta

from app.api import deps
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
from app.admin.schemas.unified_updates import AdminAccountCommand, UnifiedAccountUpdateRequest
from app.admin.services.credit_account_admin_svc import CreditAccountAdminService
from app.models.enums import CCMAccountStatus
from app.core.exceptions import BankGradeException

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

@router.patch("/{credit_account_id}")
def update_credit_account_unified(
    req: UnifiedAccountUpdateRequest,
    credit_account_id: UUID = Path(...),
    command: AdminAccountCommand = Query(...),
    db: Session = Depends(deps.get_db),
    admin=Depends(deps.get_current_admin_user)
):
    """
    Unified endpoint for credit account updates.
    Supported commands: limit, status, freeze, billing_cycle, risk, interest, overlimit.
    Strictly validates that only the relevant command field is provided.
    """
    # 1. Strict Validation: Ensure ONLY the field matching the command is present
    fields = {
        AdminAccountCommand.LIMIT: "limits",
        AdminAccountCommand.STATUS: "status",
        AdminAccountCommand.FREEZE: "freeze",
        AdminAccountCommand.BILLING_CYCLE: "billing_cycle",
        AdminAccountCommand.RISK: "risk",
        AdminAccountCommand.INTEREST: "interest",
        AdminAccountCommand.OVERLIMIT: "overlimit"
    }
    
    active_field = fields.get(command)
    
    # Check for extra fields
    provided_fields = [f for f, v in req.model_dump().items() if v is not None]
    
    if active_field not in provided_fields:
        raise BankGradeException(
            status_code=422,
            code="ZBANQ-42.2-001",
            message=f"The command '{command.value}' requires the '{active_field}' field in the request body.",
            details={"command": command.value, "required_field": active_field}
        )
        
    extra_fields = [f for f in provided_fields if f != active_field]
    if extra_fields:
        raise BankGradeException(
            status_code=422,
            code="ZBANQ-42.2-002",
            message=f"The command '{command.value}' doesn't accept values for these fields: {', '.join(extra_fields)}",
            details={"command": command.value, "invalid_fields": extra_fields}
        )

    # 2. Dispatch to specific service methods and return appropriate response
    if command == AdminAccountCommand.LIMIT:
        account, old_limit = CreditAccountAdminService.update_limit(db, credit_account_id, req.limits, admin.id)
        return {
            "credit_account_id": account.id,
            "old_credit_limit": old_limit,
            "new_credit_limit": account.credit_limit,
            "available_credit": account.available_credit,
            "updated_by": admin.id,
            "updated_at": datetime.now()
        }
        
    elif command == AdminAccountCommand.STATUS:
        account, old_status = CreditAccountAdminService.update_status(db, credit_account_id, req.status)
        return {
            "credit_account_id": account.id,
            "previous_status": old_status,
            "new_status": account.status,
            "updated_at": datetime.now()
        }
        
    elif command == AdminAccountCommand.FREEZE:
        account, new_status = CreditAccountAdminService.freeze(db, credit_account_id, req.freeze)
        return {
            "credit_account_id": account.id,
            "freeze_status": "FROZEN" if req.freeze.freeze else "ACTIVE",
            "reason_code": req.freeze.reason_code,
            "updated_at": datetime.now()
        }
        
    elif command == AdminAccountCommand.BILLING_CYCLE:
        account, old_day, old_grace = CreditAccountAdminService.update_billing_cycle(db, credit_account_id, req.billing_cycle)
        # Simple projection for next statement date (fictional logic for response)
        next_date = datetime.now() + timedelta(days=30)
        return {
            "credit_account_id": account.id,
            "old_billing_cycle_day": old_day,
            "old_grace_period": old_grace,
            "new_billing_cycle_day": account.billing_cycle_day,
            "new_grace_period": account.payment_due_days,
            "next_statement_date": next_date
        }
        
    elif command == AdminAccountCommand.RISK:
        account, old_risk = CreditAccountAdminService.update_risk_flag(db, credit_account_id, req.risk)
        return {
            "credit_account_id": account.id,
            "old_risk_flag": old_risk,
            "new_risk_flag": account.risk_flag,
            "updated_at": datetime.now()
        }
        
    elif command == AdminAccountCommand.INTEREST:
        account, old_p, old_c, old_pen = CreditAccountAdminService.update_interest(db, credit_account_id, req.interest)
        return {
            "credit_account_id": account.id,
            "old_purchase_apr": old_p,
            "old_cash_apr": old_c,
            "old_penalty_apr": old_pen,
            "purchase_apr": account.purchase_apr,
            "cash_apr": account.cash_apr,
            "penalty_apr": account.penalty_apr
        }
        
    elif command == AdminAccountCommand.OVERLIMIT:
        account, old_en, old_buf, old_fee = CreditAccountAdminService.update_overlimit(db, credit_account_id, req.overlimit)
        return {
            "credit_account_id": account.id,
            "old_overlimit_enabled": old_en,
            "old_overlimit_buffer": old_buf,
            "old_overlimit_fee": old_fee,
            "overlimit_enabled": account.overlimit_enabled,
            "overlimit_buffer": account.overlimit_buffer,
            "overlimit_fee": account.overlimit_fee
        }
    
    raise BankGradeException(status_code=400, message="Invalid command")
