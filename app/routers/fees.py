from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_async_db
from app.core.rbac import require, AuthenticatedPrincipal
from app.schemas.engine_schemas import (
    AssessFeeReq,
    AssessFeeResp
)
from app.services.fee_evaluator import FeeEvaluator

router = APIRouter(tags=["Fees"])

@router.post(
    "/cards/{card_id}/fees",
    response_model=AssessFeeResp,
    status_code=201,
    summary="Assess Fee",
    description="""
FUNCTIONALITY:
Allows management to manually associate ad-hoc, late, or annual fees securely tied to an issued card and account.

ROLES THAT CAN ACCESS THE ENDPOINT:
- MANAGER

MATH FORMULA: N/A

LOGIC AND NECESSITY OF THE ENDPOINT:
Fees accumulate and remain unassociated until the next bill generation cycle safely compiles them into the total_due parameter avoiding premature mathematical evaluations.

Enums for 'fee_type':
- LATE_FEE
- ANNUAL_FEE
- OVERLIMIT_FEE
- RETURNED_PAYMENT_FEE
"""
)
async def assess_fee(
    card_id: str,
    request: AssessFeeReq,
    db: AsyncSession = Depends(get_async_db),
    principal: AuthenticatedPrincipal = Depends(require("fee:create"))
):
    result = await FeeEvaluator.assess_fee(db, card_id, request, principal.user_id)
    return result
