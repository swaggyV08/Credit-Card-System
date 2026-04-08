from fastapi import APIRouter, Depends, Query, Path
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional
from datetime import datetime, timedelta, timezone

from app.api import deps
from app.core.rbac import require, AuthenticatedPrincipal
from app.schemas.base import envelope_success
from app.schemas.responses import CreditAccountListResponse, CreditAccountUpdateResponse
from app.admin.schemas.credit_account_admin import CreditAccountDetail
from app.admin.schemas.unified_updates import AdminAccountCommand, UnifiedAccountUpdateRequest
from app.admin.services.credit_account_admin_svc import CreditAccountAdminService
from app.models.enums import CCMAccountStatus
from app.core.app_error import AppError

router = APIRouter(prefix="/credit-accounts", tags=["Admin: Credit Accounts"])

@router.get("/", response_model=CreditAccountListResponse)
def list_accounts(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[CCMAccountStatus] = None,
    product_code: Optional[str] = None,
    db: Session = Depends(deps.get_db),
    principal: AuthenticatedPrincipal = Depends(require("credit_account:list"))
):
    """
    Retrieves a paginated list of credit accounts with optional filters.

    **What it does:**
    Returns all credit accounts in the system. Supports filtering by account
    lifecycle status and product code for operational dashboards and audits.

    **Query Parameters:**
    - `status`: `PENDING` | `ACTIVE` | `SUSPENDED` | `FROZEN` | `DELINQUENT` | `CLOSED` | `CHARGED_OFF`
    - `product_code`: Filter by the linked credit product code string
    - `page` / `limit`: Pagination controls

    **Roles:** `credit_account:list` (Admin / Super Admin only)

    **Response:** `{ page, limit, total_records, accounts: [...] }`
    """
    accounts, total = CreditAccountAdminService.list_accounts(
        db, page=page, limit=limit, status=status, product_code=product_code
    )
    accounts_dump = [a.model_dump(mode='json') if hasattr(a, 'model_dump') else a for a in accounts]
    return envelope_success({
        "page": page,
        "limit": limit,
        "total_records": total,
        "accounts": accounts_dump
    })

@router.get("/{credit_account_id}")
def get_account_details(
    credit_account_id: UUID = Path(...),
    db: Session = Depends(deps.get_db),
    principal: AuthenticatedPrincipal = Depends(require("credit_account:detail"))
):
    """
    Retrieves full details of a single credit account.

    **What it does:**
    Returns the complete financial snapshot of a credit account including
    credit limit, available credit, outstanding balance, APR configuration,
    billing cycle, risk flags, overlimit settings, and version number.

    **Roles:** `credit_account:detail` (Admin / Super Admin only)

    **Response:** `CreditAccountDetail` schema with all financial fields.
    """
    acc = CreditAccountAdminService.get_account(db, credit_account_id)
    return envelope_success(acc.model_dump(mode='json') if hasattr(acc, 'model_dump') else acc)

@router.put("/{credit_account_id}", response_model=CreditAccountUpdateResponse)
def update_credit_account_unified(
    req: UnifiedAccountUpdateRequest,
    credit_account_id: UUID = Path(...),
    command: AdminAccountCommand = Query(...),
    db: Session = Depends(deps.get_db),
    principal: AuthenticatedPrincipal = Depends(require("credit_account:update"))
):
    """
    Unified endpoint for credit account updates via command dispatch.

    **What it does:**
    A single PATCH endpoint that accepts a `command` query parameter to determine
    which aspect of the credit account to modify. Only the field matching the
    command is accepted in the request body — extra fields will be rejected.

    **Query Parameter `command` (enum `AdminAccountCommand`):**
    - `limit` — Change credit limit (requires `limits` body)
    - `status` — Transition account status (requires `status` body)
    - `freeze` — Freeze or unfreeze account (requires `freeze` body)
    - `billing_cycle` — Update billing cycle day and grace period (requires `billing_cycle` body)
    - `risk` — Set risk flag (requires `risk` body)
    - `interest` — Modify APR rates (requires `interest` body)
    - `overlimit` — Configure overlimit buffer and fees (requires `overlimit` body)

    **Enums used in sub-request bodies:**
    - `CCMAccountStatus`: `PENDING` | `ACTIVE` | `SUSPENDED` | `FROZEN` | `DELINQUENT` | `CLOSED` | `CHARGED_OFF`
    - `CCMAccountRiskFlag`: `NONE` | `LOW_RISK` | `MEDIUM_RISK` | `HIGH_RISK` | `CRITICAL`
    - `CCMLimitReasonCode`: `INCOME_REVIEW` | `RISK_ADJUSTMENT` | `PROMOTIONAL` | `MANUAL_OVERRIDE`
    - `CCMStatusReasonCode`: `KYC_REVIEW` | `FRAUD_ALERT` | `DELINQUENCY` | `CUSTOMER_REQUEST` | `COMPLIANCE` | `ADMIN_ACTION`

    **Roles:** `credit_account:update` (Admin / Super Admin only)

    **Response:** Varies by command — returns old and new values for the modified field.
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
    provided_fields = [f for f, v in req.model_dump().items() if v is not None]
    
    if active_field not in provided_fields:
        raise AppError(
            code="MISSING_FIELD",
            message=f"The command '{command.value}' requires the '{active_field}' field in the request body.",
            http_status=422
        )
        
    extra_fields = [f for f in provided_fields if f != active_field]
    if extra_fields:
        raise AppError(
            code="INVALID_PAYLOAD",
            message=f"The command '{command.value}' doesn't accept values for these fields: {', '.join(extra_fields)}",
            http_status=422
        )

    # 2. Dispatch to specific service methods and return appropriate response
    if command == AdminAccountCommand.LIMIT:
        account, old_limit = CreditAccountAdminService.update_limit(db, credit_account_id, req.limits, principal.user_id)
        result = {
            "credit_account_id": str(account.id),
            "old_credit_limit": str(old_limit),
            "new_credit_limit": str(account.credit_limit),
            "available_credit": str(account.available_credit),
            "updated_by": principal.user_id,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
    elif command == AdminAccountCommand.STATUS:
        account, old_status = CreditAccountAdminService.update_status(db, credit_account_id, req.status)
        result = {
            "credit_account_id": str(account.id),
            "previous_status": old_status.value if hasattr(old_status, 'value') else old_status,
            "new_status": account.status.value if hasattr(account.status, 'value') else account.status,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
    elif command == AdminAccountCommand.FREEZE:
        account, new_status = CreditAccountAdminService.freeze(db, credit_account_id, req.freeze)
        result = {
            "credit_account_id": str(account.id),
            "freeze_status": "FROZEN" if req.freeze.freeze else "ACTIVE",
            "reason_code": req.freeze.reason_code,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
    elif command == AdminAccountCommand.BILLING_CYCLE:
        account, old_day, old_grace = CreditAccountAdminService.update_billing_cycle(db, credit_account_id, req.billing_cycle)
        next_date = datetime.now(timezone.utc) + timedelta(days=30)
        result = {
            "credit_account_id": str(account.id),
            "old_billing_cycle_day": old_day,
            "old_grace_period": old_grace,
            "new_billing_cycle_day": account.billing_cycle_day,
            "new_grace_period": account.payment_due_days,
            "next_statement_date": next_date.isoformat()
        }
        
    elif command == AdminAccountCommand.RISK:
        account, old_risk = CreditAccountAdminService.update_risk_flag(db, credit_account_id, req.risk)
        result = {
            "credit_account_id": str(account.id),
            "old_risk_flag": old_risk,
            "new_risk_flag": account.risk_flag,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
    elif command == AdminAccountCommand.INTEREST:
        account, old_p, old_c, old_pen = CreditAccountAdminService.update_interest(db, credit_account_id, req.interest)
        result = {
            "credit_account_id": str(account.id),
            "old_purchase_apr": str(old_p),
            "old_cash_apr": str(old_c),
            "old_penalty_apr": str(old_pen),
            "purchase_apr": str(account.purchase_apr),
            "cash_apr": str(account.cash_apr),
            "penalty_apr": str(account.penalty_apr)
        }
        
    elif command == AdminAccountCommand.OVERLIMIT:
        account, old_en, old_buf, old_fee = CreditAccountAdminService.update_overlimit(db, credit_account_id, req.overlimit)
        result = {
            "credit_account_id": str(account.id),
            "old_overlimit_enabled": old_en,
            "old_overlimit_buffer": str(old_buf),
            "old_overlimit_fee": str(old_fee),
            "overlimit_enabled": account.overlimit_enabled,
            "overlimit_buffer": str(account.overlimit_buffer),
            "overlimit_fee": str(account.overlimit_fee)
        }
    else:
        raise AppError(code="INVALID_COMMAND", message="Invalid command", http_status=400)
        
    return envelope_success(result)
