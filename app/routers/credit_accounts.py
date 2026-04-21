from fastapi import APIRouter, Depends, Query, Path, Header
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional, Literal
from datetime import datetime, timedelta, timezone

from app.api import deps
from app.core.rbac import require, AuthenticatedPrincipal
from app.schemas.base import envelope_success, build_pagination, ResponseEnvelope
from typing import Union
from app.schemas.responses import CreditAccountListResponse, CreditAccountUpdateResponse
from app.admin.schemas.credit_account_admin import CreditAccountDetail
from app.admin.schemas.unified_updates import AdminAccountCommand, UnifiedAccountUpdateRequest
from app.admin.services.credit_account_admin_svc import CreditAccountAdminService
from app.models.enums import CCMAccountStatus
from app.core.app_error import AppError

router = APIRouter(prefix="/credit-accounts", tags=["Admin: Credit Accounts"])

@router.get(
    "/",
    summary="Get Credit Accounts",
    description="""
**Unified endpoint to retrieve credit accounts.**

### Commands
- `command=all` — Returns a paginated list of credit accounts with optional filters.
- `command=by_id` — Returns full details of a single credit account (requires `credit_account_id` header).

### Query Parameters
- `status`: `PENDING` | `ACTIVE` | `SUSPENDED` | `FROZEN` | `DELINQUENT` | `CLOSED` | `CHARGED_OFF`
- `product_code`: Filter by linked credit product code
- `page`, `limit`: Pagination controls

### Example Success Response (command=all)
```json
{
  "status": "success",
  "data": {
    "page": 1,
    "limit": 20,
    "total_records": 1,
    "accounts": [
      {
        "credit_account_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
        "readable_id": "ACC-000001",
        "user_id": "ZNBNQ000001",
        "credit_limit": "500000.00",
        "available_credit": "450000.00",
        "outstanding_balance": "50000.00",
        "status": "ACTIVE",
        "billing_cycle_day": 15,
        "risk_flag": "NONE"
      }
    ]
  },
  "meta": {
    "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "timestamp": "2026-04-08T10:30:00.000000+00:00",
    "api_version": "1.0.0"
  },
  "errors": []
}
```

### Example Success Response (command=by_id)
```json
{
  "status": "success",
  "data": {
    "credit_account_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "readable_id": "ACC-000001",
    "user_id": "ZNBNQ000001",
    "credit_limit": "500000.00",
    "available_credit": "450000.00",
    "outstanding_balance": "50000.00",
    "cash_advance_limit": "100000.00",
    "status": "ACTIVE",
    "billing_cycle_day": 15,
    "payment_due_days": 20,
    "purchase_apr": "36.00",
    "cash_apr": "42.00",
    "penalty_apr": "48.00",
    "overlimit_enabled": false,
    "overlimit_buffer": "0.00",
    "overlimit_fee": "0.00",
    "risk_flag": "NONE",
    "version": 1,
    "opened_at": "2026-04-08T10:30:00+00:00"
  },
  "meta": { ... },
  "errors": []
}
```

**Roles:** `credit_account:list`, `credit_account:detail` (Admin / Manager / SuperAdmin)
""",
    response_model=Union[ResponseEnvelope[CreditAccountDetail], CreditAccountListResponse]
)
def get_credit_accounts(
    command: Literal["all", "by_id"] = Query(..., description="Action to perform"),
    credit_account_id: Optional[UUID] = Header(None, description="Required for command=by_id"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[CCMAccountStatus] = None,
    product_code: Optional[str] = None,
    db: Session = Depends(deps.get_db),
    principal: AuthenticatedPrincipal = Depends(require("credit_account:list"))
):
    if command == "by_id":
        if not credit_account_id:
            raise AppError(code="MISSING_ACCOUNT_ID", message="credit_account_id header is required for command=by_id", http_status=422)
        
        acc = CreditAccountAdminService.get_account(db, credit_account_id)
        return envelope_success(acc.model_dump(mode='json') if hasattr(acc, 'model_dump') else acc)

    elif command == "all":
        accounts, total = CreditAccountAdminService.list_accounts(
            db, page=page, limit=limit, status=status, product_code=product_code
        )
        accounts_dump = [a.model_dump(mode='json') if hasattr(a, 'model_dump') else a for a in accounts]
        return envelope_success({
            "accounts": accounts_dump,
            "pagination": build_pagination(total, page, limit)
        })

@router.put(
    "/{credit_account_id}",
    summary="Update Credit Account Unified",
    description="""
**Unified endpoint for credit account updates via command dispatch.**

### Commands (query parameter)
- `limit` — Change credit limit (requires `limits` body)
- `status` — Transition account status (requires `status` body)
- `freeze` — Freeze or unfreeze account (requires `freeze` body)
- `billing_cycle` — Update billing cycle day and grace period (requires `billing_cycle` body)
- `risk` — Set risk flag (requires `risk` body)

### Request Body
Only provide the field that matches the command. Extra fields will be rejected.
```json
{
  "limits": {
    "new_credit_limit": "0000000000.000",
    "reason_code": "INCOME_REVIEW",
    "notes": "string",
    "effective_from": "2026-06-01"
  },
  "status": {
    "status": "PENDING",
    "reason_code": "KYC_REVIEW",
    "notes": "string"
  },
  "freeze": {
    "freeze": true,
    "reason_code": "KYC_REVIEW",
    "notes": "string"
  },
  "billing_cycle": {
    "billing_cycle_day": 1,
    "grace_period": 1
  },
  "risk": {
    "risk_flag": "NONE",
    "reason": "string"
  }
}
```

### Enums
- `CCMAccountStatus`: `PENDING` | `ACTIVE` | `SUSPENDED` | `FROZEN` | `DELINQUENT` | `CLOSED` | `CHARGED_OFF`
- `CCMAccountRiskFlag`: `NONE` | `LOW_RISK` | `MEDIUM_RISK` | `HIGH_RISK` | `CRITICAL`
- `CCMLimitReasonCode`: `INCOME_REVIEW` | `RISK_ADJUSTMENT` | `PROMOTIONAL` | `MANUAL_OVERRIDE`
- `CCMStatusReasonCode`: `KYC_REVIEW` | `FRAUD_ALERT` | `DELINQUENCY` | `CUSTOMER_REQUEST` | `COMPLIANCE` | `ADMIN_ACTION`

**Roles:** `credit_account:update` (Admin / SuperAdmin only)
""",
    response_model=CreditAccountUpdateResponse
)
def update_credit_account_unified(
    req: UnifiedAccountUpdateRequest,
    credit_account_id: UUID = Path(...),
    command: AdminAccountCommand = Query(...),
    db: Session = Depends(deps.get_db),
    principal: AuthenticatedPrincipal = Depends(require("credit_account:update"))
):
    # Block removed commands
    if command in (AdminAccountCommand.INTEREST, AdminAccountCommand.OVERLIMIT):
        raise AppError(
            code="INVALID_COMMAND",
            message=f"Command '{command.value}' is not supported. Allowed: limit, status, freeze, billing_cycle, risk",
            http_status=400
        )

    # Strict Validation: Ensure ONLY the field matching the command is present
    fields = {
        AdminAccountCommand.LIMIT: "limits",
        AdminAccountCommand.STATUS: "status",
        AdminAccountCommand.FREEZE: "freeze",
        AdminAccountCommand.BILLING_CYCLE: "billing_cycle",
        AdminAccountCommand.RISK: "risk",
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
    else:
        raise AppError(code="INVALID_COMMAND", message="Invalid command", http_status=400)
        
    return envelope_success(result)
