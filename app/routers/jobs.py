from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.api.deps import get_async_db
from app.core.rbac import require, AuthenticatedPrincipal
from app.schemas.engine_schemas import (
    ProcessClearingResp,
    SettlementReq,
    ProcessSettlementResp
)
from app.services.batch_processing import BatchProcessingEngine

router = APIRouter(tags=["Jobs"])

@router.post(
    "/jobs/clearing/{cycle_date}",
    response_model=ProcessClearingResp,
    status_code=200,
    summary="Process Clearing",
    description="""
FUNCTIONALITY:
Batch job moving all AUTHORIZED transactions into CLEARED parameters. Releases hold_amount from the available_credit array natively, posting the hard settled bounds directly. Process works atomically individually resolving isolation.

ROLES THAT CAN ACCESS THE ENDPOINT:
- ADMIN
- SUPERADMIN

MATH FORMULA:
total_amount_cleared = SUM(transaction.amount) (where status=AUTHORIZED)

LOGIC AND NECESSITY OF THE ENDPOINT:
Fundamental batch workflow completing the physical transfer stages of authorized money holds allowing subsequent bill generation pipelines to intercept cleared items natively.
"""
)
async def process_clearing(
    cycle_date: str,
    db: AsyncSession = Depends(get_async_db),
    principal: AuthenticatedPrincipal = Depends(require("admin:all"))
):
    result = await BatchProcessingEngine.process_clearing(db, cycle_date, principal.user_id)
    return result


@router.post(
    "/jobs/settlements/{settlement_date}",
    response_model=ProcessSettlementResp,
    status_code=200,
    summary="Process Settlement",
    description="""
FUNCTIONALITY:
Completes financial routing translating CLEARED items to SETTLED states allowing payment distribution. 

ROLES THAT CAN ACCESS THE ENDPOINT:
- ADMIN
- SUPERADMIN

MATH FORMULA:
net_issuer_obligation = SUM(settled items) * 0.98

LOGIC AND NECESSITY OF THE ENDPOINT:
Settlement represents the exact institutional settlement obligation boundary processing funds transfer computationally against all cleared instances natively checking bounds per target date sequentially.
"""
)
async def process_settlement(
    settlement_date: str,
    request: SettlementReq,
    db: AsyncSession = Depends(get_async_db),
    principal: AuthenticatedPrincipal = Depends(require("admin:all"))
):
    # Note: settlement_date is technically in path, but user allowed mapping exactly
    result = await BatchProcessingEngine.process_settlement(db, settlement_date, request, principal.user_id)
    return result
