from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.api.deps import get_async_db
from app.core.rbac import require, AuthenticatedPrincipal
from app.schemas.engine_schemas import (
    ProcessPaymentReq,
    ProcessPaymentResp
)
from app.services.payment_engine import PaymentEngine

router = APIRouter(tags=["Payments"])

@router.post(
    "/credit-account/{credit_account_id}/payment/{bill_id}",
    response_model=ProcessPaymentResp,
    status_code=200,
    summary="Process Payment",
    description="""
FUNCTIONALITY:
Atomically processes a full or partial payment recovering available credit on real-time transaction boundaries, while updating the Bill status correspondingly. The endpoint maps securely resolving bounds on the specific unpaid bill instance.

ROLES THAT CAN ACCESS THE ENDPOINT:
- USER (own card only)

MATH FORMULA:
available_credit_after = min(credit_limit, available_credit_before + amount_paid)
remaining_due = total_due_before - amount_paid

LOGIC AND NECESSITY OF THE ENDPOINT:
Fundamental for user payment processing. Guaranteed strictly preventing overpayments mapping exact bounds via FULL, PARTIAL, or MINIMUM ENUMS natively configured avoiding decimal leakage vulnerabilities.

Enums for 'payment_type':
- FULL
- PARTIAL
- MINIMUM
"""
)
async def process_payment(
    credit_account_id: str,
    bill_id: str,
    request: ProcessPaymentReq,
    db: AsyncSession = Depends(get_async_db),
    principal: AuthenticatedPrincipal = Depends(require("payment:create"))
):
    result = await PaymentEngine.process(
        db=db,
        credit_account_id=credit_account_id,
        bill_id=bill_id,
        user_id=principal.user_id,
        payload=request
    )
    return result
